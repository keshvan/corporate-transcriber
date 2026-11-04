from pydantic import BaseModel, Field


class Segment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    label: str | None = None

class SpeakerInfo(BaseModel):
    label: str
    person_id: str | None = None
    name: str | None = None
    score: float | None = None

class Transcript(BaseModel):
    language: str
    duration_ms: int
    asr_model: str
    segments: list[Segment]
    speakers: list[SpeakerInfo] = Field(default_factory=list)
