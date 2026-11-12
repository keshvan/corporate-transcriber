import logging
from collections.abc import Sequence
from uuid import UUID

from psycopg import Connection
from psycopg_pool import ConnectionPool

from app.domain import SpeakerOutcome
from app.schemas.transcript import Transcript
from app.storage.processed_events import record_current_event

log = logging.getLogger("meeting_repository")


class MeetingNotFoundError(LookupError):
    def __init__(self, meeting_id: str) -> None:
        super().__init__(f"meeting {meeting_id} does not exist")
        self.meeting_id = meeting_id


_MEETING_EXISTS = "SELECT 1 FROM meetings WHERE id = %s"

_UPSERT_TRANSCRIPT = """
INSERT INTO transcripts (meeting_id, full_text, language, model)
VALUES (%s, %s, %s, %s)
ON CONFLICT (meeting_id) DO UPDATE SET
    full_text = EXCLUDED.full_text,
    language  = EXCLUDED.language,
    model     = EXCLUDED.model
RETURNING id
"""

_UPSERT_SPEAKERS = """
INSERT INTO meeting_speakers
    (meeting_id, label, speech_ms, qdrant_point_id, embedding_status,
     suggested_person_id, suggested_score)
SELECT %(meeting_id)s::uuid, t.label, t.speech_ms, t.point_id, t.status, t.person_id, t.score
FROM unnest(
    %(labels)s::text[],
    %(speech_ms)s::int[],
    %(point_ids)s::uuid[],
    %(statuses)s::text[],
    %(person_ids)s::text[],
    %(scores)s::float8[]
) AS t(label, speech_ms, point_id, status, person_id, score)
ON CONFLICT (meeting_id, label) DO UPDATE SET
    speech_ms           = EXCLUDED.speech_ms,
    qdrant_point_id     = EXCLUDED.qdrant_point_id,
    embedding_status    = EXCLUDED.embedding_status,
    suggested_person_id = EXCLUDED.suggested_person_id,
    suggested_score     = EXCLUDED.suggested_score
RETURNING label, id
"""

_UPSERT_SEGMENT = """
INSERT INTO transcript_segments
    (transcript_id, meeting_speaker_id, segment_index, text, start_ms, end_ms)
VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (transcript_id, segment_index) DO UPDATE SET
    meeting_speaker_id = EXCLUDED.meeting_speaker_id,
    text               = EXCLUDED.text,
    start_ms           = EXCLUDED.start_ms,
    end_ms             = EXCLUDED.end_ms
"""

_DELETE_SEGMENT_TAIL = """
DELETE FROM transcript_segments WHERE transcript_id = %s AND segment_index >= %s
"""


class PostgresMeetingResultRepository:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def ensure_meeting_exists(self, meeting_id: str) -> None:
        with self._pool.connection() as conn:
            self._require_meeting(conn, UUID(meeting_id))

    def save(
        self,
        meeting_id: str,
        transcript: Transcript,
        speakers: Sequence[SpeakerOutcome],
    ) -> None:
        mid = UUID(meeting_id)
        with self._pool.connection() as conn, conn.transaction():
            self._require_meeting(conn, mid)
            transcript_id = self._upsert_transcript(conn, mid, transcript)
            speaker_ids = self._upsert_speakers(conn, mid, speakers)
            self._replace_segments(conn, transcript_id, transcript, speaker_ids)
            record_current_event(conn, mid)
        log.info(
            "meeting result saved",
            extra={
                "meeting_id": meeting_id,
                "segments": len(transcript.segments),
                "speakers": len(speakers),
            },
        )

    @staticmethod
    def _require_meeting(conn: Connection, meeting_id: UUID) -> None:
        if conn.execute(_MEETING_EXISTS, (meeting_id,)).fetchone() is None:
            raise MeetingNotFoundError(str(meeting_id))

    @staticmethod
    def _upsert_transcript(conn: Connection, meeting_id: UUID, transcript: Transcript) -> UUID:
        full_text = " ".join(s.text.strip() for s in transcript.segments if s.text.strip())
        row = conn.execute(
            _UPSERT_TRANSCRIPT,
            (meeting_id, full_text, transcript.language or None, transcript.asr_model),
        ).fetchone()
        return row[0] # type: ignore

    @staticmethod
    def _upsert_speakers(
        conn: Connection, meeting_id: UUID, speakers: Sequence[SpeakerOutcome]
    ) -> dict[str, UUID]:
        unique = {s.label: s for s in speakers}
        if not unique:
            return {}
        items = list(unique.values())
        rows = conn.execute(
            _UPSERT_SPEAKERS,
            {
                "meeting_id": meeting_id,
                "labels": [s.label for s in items],
                "speech_ms": [s.speech_ms for s in items],
                "point_ids": [s.embedding.point_id for s in items],
                "statuses": [s.embedding.status.value for s in items],
                "person_ids": [s.match.person_id if s.match else None for s in items],
                "scores": [s.match.score if s.match else None for s in items],
            },
        ).fetchall()
        return {label: speaker_id for label, speaker_id in rows}

    @staticmethod
    def _replace_segments(
        conn: Connection,
        transcript_id: UUID,
        transcript: Transcript,
        speaker_ids: dict[str, UUID],
    ) -> None:
        rows = []
        for index, seg in enumerate(transcript.segments):
            if seg.label is not None and seg.label not in speaker_ids:
                raise ValueError(f"segment {index} references unknown speaker label {seg.label!r}")
            rows.append((
                transcript_id,
                speaker_ids[seg.label] if seg.label is not None else None,
                index,
                seg.text,
                seg.start_ms,
                seg.end_ms,
            ))
        with conn.cursor() as cur:
            if rows:
                cur.executemany(_UPSERT_SEGMENT, rows)  # batch, одно соединение
            cur.execute(_DELETE_SEGMENT_TAIL, (transcript_id, len(rows)))
