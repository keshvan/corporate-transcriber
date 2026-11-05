from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpeakerTurn:
    start_ms: int
    end_ms: int
    label: str

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

@dataclass(frozen=True, eq=False)
class SpeakerEmbeddings:
    model: str
    vectors: dict[str, np.ndarray]
    speech_ms: dict[str, int]

@dataclass(frozen=True)
class SpeakerMatch:
    person_id: str
    score: float
    name: str | None = None
