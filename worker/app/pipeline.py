import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.media.ffmpeg import probe_audio, to_wav_16k_mono
from app.schemas.transcript import Transcript

log = logging.getLogger("pipeline")

class BlobStore(Protocol):
    def download_file(self, uri: str, dest: Path) -> Path: ...

class Transcriber(Protocol):
    def transcribe(self, wav: Path, language: str | None = None) -> Transcript: ...


@dataclass(frozen=True)
class TranscribeJob:
    job_id: str
    meeting_id: str
    audio_uri: str
    language: str | None = None

class TranscribePipeline:
    def __init__(
        self,
        storage: BlobStore,
        asr: Transcriber
    ) -> None:
        self._storage = storage
        self._asr = asr

    def run(self, job: TranscribeJob) -> Transcript:
        ids = {"job_id": job.job_id, "meeting_id": job.meeting_id}
        log.info("pipeline started", extra=ids)

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

            log.info("job finished", extra=ids)
            return transcript
