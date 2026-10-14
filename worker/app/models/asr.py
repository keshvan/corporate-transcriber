from __future__ import annotations

from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

from app.config import Settings
from app.schemas.transcript import Segment, Transcript


class WhisperTranscriber:
    def __init__(
        self,
        model_name: str,
        device: str,
        compute_type: str,
        models_dir: str | None = None,
        beam_size: int = 5,
    ) -> None:
        self._model_name = model_name
        self._beam_size = beam_size
        self._model = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
            download_root=models_dir,
        )

    @classmethod
    def from_settings(cls, s: Settings) -> WhisperTranscriber:
        return cls(
            model_name=s.worker_whisper_model,
            device=s.worker_device,
            compute_type=s.worker_compute_type,
            models_dir=s.worker_models_dir,
            beam_size=s.worker_beam_size,
        )

    def warmup(self) -> None:
        silence = np.zeros(16_000, dtype=np.float32)
        self._model.transcribe(silence)

    def transcribe(self, wav: Path, language: str | None = "ru") -> Transcript:
        segments, info = self._model.transcribe(
            str(wav),
            language=language,
            beam_size=self._beam_size,
            vad_filter=True
        )

        result = [
            Segment(start_ms=round(s.start * 1000), end_ms=round(s.end * 1000), text=s.text.strip())
            for s in segments
            if s.text.strip()
        ]
        return Transcript(
            language=info.language,
            duration_ms=round(info.duration * 1000),
            asr_model=self._model_name,
            segments=result,
        )
