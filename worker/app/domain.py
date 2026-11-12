from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

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

class EmbeddingStatus(str, Enum):
    SAVED = "saved"
    NO_EMBEDDING = "no_embedding"
    INSUFFICIENT_SPEECH = "insufficient_speech"
    FAILED = "failed"

@dataclass(frozen=True)
class EmbeddingSaveResult:
    status: EmbeddingStatus
    point_id: str | None = None

    def __post_init__(self) -> None:
        if (self.status is EmbeddingStatus.SAVED) != (self.point_id is not None):
            raise ValueError("point_id must be set if and only if status is SAVED")

@dataclass(frozen=True)
class SpeakerOutcome:
    label: str
    speech_ms: int | None
    embedding: EmbeddingSaveResult
    match: SpeakerMatch | None = None
