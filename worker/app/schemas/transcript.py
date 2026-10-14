from pydantic import BaseModel


class Segment(BaseModel):
    start_ms: int
    end_ms: int
    text: str
    speaker: str | None = None

class Transcript(BaseModel):
    language: str
    duration_ms: int
    asr_model: str
    segments: list[Segment]
