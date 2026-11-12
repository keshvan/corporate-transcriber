from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

from pydantic import BaseModel, ConfigDict

_MAX_ORIGINAL_BYTES: Final = 64 * 1024

class MeetingProcessingPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    meeting_id: UUID
    audio_object_key: str
    language: str | None = None

class MeetingProcessingRequested(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: UUID
    correlation_id: str | None = None
    payload: MeetingProcessingPayload

@dataclass(frozen=True)
class ConsumedMessage:
    topic: str
    partition: int
    offset: int
    key: bytes | None
    value: bytes | None


class DeadLetter(BaseModel):
    dlq_schema_version: int = 1
    event_id: str | None
    source_topic: str
    source_partition: int
    source_offset: int
    error_type: str
    error_description: str
    attempts: int
    retries_exhausted: bool
    failed_at: datetime
    original_message: str | None
    original_message_base64: str | None
    original_message_truncated: bool

    @classmethod
    def create(
        cls,
        *,
        topic: str,
        partition: int,
        offset: int,
        value: bytes | None,
        event_id: str | None,
        error_type: str,
        error_description: str,
        attempts: int,
        retries_exhausted: bool,
    ) -> DeadLetter:
        chunk = value[:_MAX_ORIGINAL_BYTES] if value is not None else None
        return cls(
            event_id=event_id,
            source_topic=topic,
            source_partition=partition,
            source_offset=offset,
            error_type=error_type,
            error_description=error_description,
            attempts=attempts,
            retries_exhausted=retries_exhausted,
            failed_at=datetime.now(UTC),
            original_message=chunk.decode("utf-8", errors="replace") if chunk is not None else None,
            original_message_base64=(
                base64.b64encode(chunk).decode("ascii") if chunk is not None else None
            ),
            original_message_truncated=value is not None and len(value) > _MAX_ORIGINAL_BYTES,
        )
