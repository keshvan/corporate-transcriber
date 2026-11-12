from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import psycopg

from app.media.errors import InvalidMediaError, MediaToolError
from app.storage.errors import ObjectNotFoundError, StorageError
from app.storage.meeting_repository import MeetingNotFoundError

_MAX_DESCRIPTION = 500

class EventError(Exception):
    def __init__(self, error_type: str, message: str, event_id: str | None = None) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.event_id = event_id

class DlqPublishError(RuntimeError): ...

class CommitFailedError(RuntimeError): ...

class KafkaFatalError(RuntimeError): ...

class FailureKind(str, Enum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"

@dataclass(frozen=True)
class Failure:
    kind: FailureKind
    error_type: str
    description: str

def _describe(exc: BaseException) -> str:
    text = " ".join(str(exc).split())[:_MAX_DESCRIPTION]
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__

def classify(exc: BaseException) -> Failure:
    description = _describe(exc)
    if isinstance(exc, EventError):
        return Failure(FailureKind.PERMANENT, exc.error_type, description)
    if isinstance(exc, InvalidMediaError):
        return Failure(FailureKind.PERMANENT, "invalid_media", description)
    if isinstance(exc, ObjectNotFoundError):
        return Failure(FailureKind.TRANSIENT, "audio_not_found", description)
    if isinstance(exc, MeetingNotFoundError):
        return Failure(FailureKind.TRANSIENT, "meeting_not_found", description)
    if isinstance(exc, StorageError):
        return Failure(FailureKind.TRANSIENT, "storage_error", description)
    if isinstance(exc, MediaToolError):
        return Failure(FailureKind.TRANSIENT, "media_tool_error", description)
    if isinstance(exc, psycopg.Error):
        return Failure(FailureKind.TRANSIENT, "postgres_error", description)
    return Failure(FailureKind.TRANSIENT, "unexpected_error", description)
