import logging
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.domain import (
    EmbeddingSaveResult,
    EmbeddingStatus,
    SpeakerEmbeddings,
    SpeakerMatch,
    SpeakerOutcome,
    SpeakerTurn,
)
from app.media.ffmpeg import probe_audio, to_wav_16k_mono
from app.schemas.transcript import Segment, SpeakerInfo, Transcript

log = logging.getLogger("pipeline")


class BlobStore(Protocol):
    def download_file(self, uri: str, dest: Path) -> Path: ...

class Transcriber(Protocol):
    def transcribe(self, wav: Path, language: str | None = None) -> Transcript: ...

class Diarizer(Protocol):
    def diarize(self, wav: Path, num_speakers: int | None = None) -> list[SpeakerTurn]: ...

class SpeakerEmbedder(Protocol):
    def embed(self, wav: Path, turns: list[SpeakerTurn]) -> SpeakerEmbeddings: ...

class SpeakerIdentifier(Protocol):
    def identify(self, embeddings: SpeakerEmbeddings) -> dict[str, SpeakerMatch | None]: ...

class SpeakerStore(Protocol):
    def save(
        self,
        meeting_id: str,
        embeddings: SpeakerEmbeddings,
        matches: Mapping[str, SpeakerMatch | None],
    ) -> dict[str, EmbeddingSaveResult]: ...

class MeetingResultRepository(Protocol):
    def ensure_meeting_exists(self, meeting_id: str) -> None: ...
    def save(
        self,
        meeting_id: str,
        transcript: Transcript,
        speakers: Sequence[SpeakerOutcome],
    ) -> None: ...

@dataclass(frozen=True)
class PipelineResult:
    transcript: Transcript
    speaker_embeddings: SpeakerEmbeddings

@dataclass(frozen=True)
class TranscribeJob:
    job_id: str
    meeting_id: str
    audio_uri: str
    language: str | None = None

def assign_labels(segments: list[Segment], turns: list[SpeakerTurn]) -> list[Segment]:
    result = []
    for seg in segments:
        overlap: dict[str, int] = defaultdict(int)
        for t in turns:
            ms = min(seg.end_ms, t.end_ms) - max(seg.start_ms, t.start_ms)
            if ms > 0:
                overlap[t.label] += ms
        label = max(overlap, key=overlap.__getitem__) if overlap else None
        result.append(seg.model_copy(update={"label": label}))
    return result

def build_speaker_outcomes(
    turns: list[SpeakerTurn],
    segments: list[Segment],
    embeddings: SpeakerEmbeddings,
    matches: Mapping[str, SpeakerMatch | None],
    saved: Mapping[str, EmbeddingSaveResult],
) -> list[SpeakerOutcome]:
    labels = (
        {t.label for t in turns}
        | {s.label for s in segments if s.label}
        | set(embeddings.vectors)
        | set(embeddings.speech_ms)
    )
    no_embedding = EmbeddingSaveResult(EmbeddingStatus.NO_EMBEDDING)
    return [
        SpeakerOutcome(
            label=label,
            speech_ms=embeddings.speech_ms.get(label),
            embedding=saved.get(label, no_embedding),
            match=matches.get(label),
        )
        for label in sorted(labels)
    ]

class TranscribePipeline:
    def __init__(
        self,
        storage: BlobStore,
        asr: Transcriber,
        diarizer: Diarizer,
        embedder: SpeakerEmbedder,
        identifier: SpeakerIdentifier,
        store: SpeakerStore,
        results: MeetingResultRepository,
    ) -> None:
        self._storage = storage
        self._asr = asr
        self._diarizer = diarizer
        self._embedder = embedder
        self._identifier = identifier
        self._store = store
        self._results = results

    def run(self, job: TranscribeJob):
        ids = {"job_id": job.job_id, "meeting_id": job.meeting_id}
        log.info("pipeline started", extra=ids)

        self._results.ensure_meeting_exists(job.meeting_id)

        with tempfile.TemporaryDirectory(prefix=f"job-{job.job_id}") as tmp:
            workdir = Path(tmp)

            raw = self._storage.download_file(job.audio_uri, workdir / "raw")
            log.info("audio downloaded", extra=ids)

            info = probe_audio(raw)
            wav = to_wav_16k_mono(raw, workdir / "16k.wav")
            log.info("audio normalized", extra={**ids, "duration_s": info.duration_s})

            transcript = self._asr.transcribe(wav, language=job.language)
            log.info(
                "transcribed",
                extra={**ids, "segments": len(transcript.segments), "language": transcript.language},
            )

            turns = self._diarizer.diarize(wav)
            log.info(
                "diarized",
                extra={**ids, "turns": len(turns), "speakers": len({t.label for t in turns})},
            )

            segments = assign_labels(transcript.segments, turns)

            embeddings = self._embedder.embed(wav, turns)
            log.info("embeddings computed", extra={**ids, "speakers": len(embeddings.vectors)})

            matches = self._identifier.identify(embeddings)
            log.info(
                "speakers identified",
                extra={**ids, "identified": sum(1 for m in matches.values() if m)},
            )

            saved = self._store.save(job.meeting_id, embeddings, matches)

            labels = sorted({s.label for s in segments if s.label})
            speakers = []
            for label in labels:
                m = matches.get(label)
                speakers.append(
                    SpeakerInfo(
                        label=label,
                        person_id=m.person_id if m else None,
                        name=m.name if m else None,
                        score=m.score if m else None,
                    )
                )

            outcomes = build_speaker_outcomes(turns, segments, embeddings, matches, saved)

            self._results.save(job.meeting_id, transcript, outcomes)
            log.info("results saved to postgres", extra={**ids, "speakers": len(outcomes)})

            log.info("job finished", extra=ids)
            return PipelineResult(transcript, embeddings)
