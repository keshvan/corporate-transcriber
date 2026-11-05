from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, PointVectors

from app.config import Settings
from app.domain import SpeakerEmbeddings, SpeakerMatch
from app.speakers.voice_collection import STATUS_UNKNOWN, Key, to_point_vector

log = logging.getLogger("speakers.store")

Payload = dict[str, object]

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "project-memory/voice-profiles")


def point_id(meeting_id: str, label: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{meeting_id}:{label}"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class _Candidate:
    point_id: str
    label: str
    vector: list[float]
    speech_ms: int
    match: SpeakerMatch | None


class QdrantSpeakerStore:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        min_speech_ms: int,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._client = client
        self._collection = collection
        self._min_speech_ms = min_speech_ms
        self._clock = clock

    @classmethod
    def from_settings(cls, client: QdrantClient, s: Settings) -> QdrantSpeakerStore:
        return cls(
            client=client,
            collection=s.qdrant_voice_collection,
            min_speech_ms=s.speaker_save_min_speech_ms,
        )

    def save(
        self,
        meeting_id: str,
        embeddings: SpeakerEmbeddings,
        matches: Mapping[str, SpeakerMatch | None],
    ) -> None:
        candidates = self._select(meeting_id, embeddings, matches)
        if not candidates:
            log.info("no speaker embeddings to save", extra={"meeting_id": meeting_id})
            return

        created_at = self._clock().isoformat()

        try:
            found = self._client.retrieve(
                collection_name=self._collection,
                ids=[c.point_id for c in candidates],
                with_payload=False,
                with_vectors=False,
            )
            existing = {str(r.id) for r in found}
        except Exception:
            log.exception(
                "speaker embeddings not saved: lookup failed",
                extra={"meeting_id": meeting_id},
            )
            return

        new = [c for c in candidates if c.point_id not in existing]
        old = [c for c in candidates if c.point_id in existing]

        if new:
            try:
                self._insert(meeting_id, embeddings.model, created_at, new)
            except Exception:
                log.exception(
                    "failed to insert new speaker embeddings",
                    extra={"meeting_id": meeting_id},
                )
        if old:
            try:
                self._update(meeting_id, embeddings.model, created_at, old)
            except Exception:
                log.exception(
                    "failed to update existing speaker embeddings",
                    extra={"meeting_id": meeting_id},
                )
        log.info(
            "speaker embeddings saved",
            extra={"meeting_id": meeting_id, "new": len(new), "updated": len(old)},
        )

    def _select(
        self,
        meeting_id: str,
        embeddings: SpeakerEmbeddings,
        matches: Mapping[str, SpeakerMatch | None],
    ) -> list[_Candidate]:
        selected: list[_Candidate] = []
        for label in sorted(embeddings.vectors):
            vector = to_point_vector(embeddings.vectors[label])
            if vector is None:
                log.warning(
                    "speaker skipped: unusable embedding",
                    extra={"meeting_id": meeting_id, "label": label},
                )
                continue
            speech_ms = embeddings.speech_ms.get(label, 0)
            if speech_ms < self._min_speech_ms:
                log.info(
                    "speaker skipped: too little speech",
                    extra={
                        "meeting_id": meeting_id,
                        "label": label,
                        "speech_ms": speech_ms,
                    },
                )
                continue
            selected.append(
                _Candidate(
                    point_id=point_id(meeting_id, label),
                    label=label,
                    vector=vector,
                    speech_ms=speech_ms,
                    match=matches.get(label),
                )
            )
        return selected

    def _insert(
        self, meeting_id: str, model: str, created_at: str, new: list[_Candidate]
    ) -> None:
        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=c.point_id,
                    vector=c.vector,
                    payload={
                        Key.STATUS: STATUS_UNKNOWN,
                        Key.PERSON_ID: None,
                        Key.PINNED: False,
                        Key.ATTACHED_AT: None,
                        **_mutable_payload(meeting_id, model, created_at, c),
                    },
                )
                for c in new
            ],
        )

    def _update(
        self, meeting_id: str, model: str, created_at: str, old: list[_Candidate]
    ) -> None:
        self._client.update_vectors(
            collection_name=self._collection,
            points=[PointVectors(id=c.point_id, vector=c.vector) for c in old],
        )

        for c in old:
            self._client.set_payload(
                collection_name=self._collection,
                payload=_mutable_payload(meeting_id, model, created_at, c),
                points=[c.point_id],
            )


def _mutable_payload(
    meeting_id: str, model: str, created_at: str, c: _Candidate
) -> Payload:
    """Поля, которые worker вправе перезаписывать."""
    return {
        Key.MEETING_ID: meeting_id,
        Key.LABEL: c.label,
        Key.MODEL: model,
        Key.SPEECH_MS: c.speech_ms,
        Key.CREATED_AT: created_at,
        Key.SUGGESTED_PERSON_ID: c.match.person_id if c.match else None,
        Key.SUGGESTED_SCORE: c.match.score if c.match else None,
    }
