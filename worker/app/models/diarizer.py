from __future__ import annotations

from pathlib import Path
from typing import cast

import soundfile as sf
import torch
from pyannote.audio import Pipeline
from pyannote.core import Annotation, Segment

from app.config import Settings
from app.domain import SpeakerTurn


class PyannoteDiarizer:
    def __init__(
        self,
        model_name: str,
        hf_token: str,
        device: str,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> None:
        pipeline = Pipeline.from_pretrained(model_name, token=hf_token)
        if pipeline is None:
            raise RuntimeError(
                f"cannot load {model_name}: check HF token and accepted model terms"
            )
        self._model_name = model_name
        self._pipeline = pipeline.to(torch.device(device))
        self._min_speakers = min_speakers
        self._max_speakers = max_speakers

    @classmethod
    def from_settings(cls, s: Settings) -> PyannoteDiarizer:
        return cls(
            model_name=s.worker_diarization_model,
            hf_token=s.hf_token.get_secret_value(),
            device=s.worker_device,
            min_speakers=s.worker_min_speakers,
            max_speakers=s.worker_max_speakers,
        )

    def diarize(self, wav: Path, num_speakers: int | None = None) -> list[SpeakerTurn]:
        data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
        audio = {
            "waveform": torch.from_numpy(data.T.copy()),
            "sample_rate": sr
        }

        exact = num_speakers is not None
        output = self._pipeline(
            audio,
            num_speakers=num_speakers,
            min_speakers=None if exact else self._min_speakers,
            max_speakers=None if exact else self._max_speakers,
        )

        annotation = cast(Annotation, getattr(output, "speaker_diarization", output))

        turns: list[SpeakerTurn] = []
        for item in annotation.itertracks(yield_label=True):
            seg, _, label = cast(tuple[Segment, str, str], item)
            turns.append(SpeakerTurn(round(seg.start * 1000), round(seg.end * 1000), str(label)))
        return turns
