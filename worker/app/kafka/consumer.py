from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Mapping, MutableMapping
from enum import Enum
from typing import Any, Final, Protocol
from uuid import UUID

from pydantic import BaseModel, ValidationError

from app.kafka.errors import (
    CommitFailedError,
    DlqPublishError,
    EventError,
    Failure,
    FailureKind,
    classify,
)
from app.pipeline import PipelineResult, TranscribeJob
from app.schemas.events import ConsumedMessage, DeadLetter, MeetingProcessingRequested
from app.storage.processed_events import recording_event

log = logging.getLogger("messaging.consumer")

_MAX_EVENT_ID_LENGTH: Final = 64

class MessageSource(Protocol):
    def poll(self, timeout_s: float) -> ConsumedMessage | None: ...

    def commit(self, message: ConsumedMessage) -> None: ...

    def keepalive(self) -> None: ...

    def resume(self) -> None: ...

    def close(self) -> None: ...

class DeadLetterSink(Protocol):
    def publish(self, key: bytes | None, record: DeadLetter) -> None: ...

    def close(self) -> None: ...

class PipelineRunner(Protocol):
    def run(self, job: TranscribeJob) -> PipelineResult: ...

class ProcessedEventsLookup(Protocol):
    def is_processed(self, event_id: UUID) -> bool: ...

class HandlingResult(str, Enum):
    PROCESSED = "processed"
    DUPLICATE = "duplicate"

class Disposition(str, Enum):
    COMPLETED = "completed"
    DEAD_LETTERED = "dead_lettered"
    ABANDONED = "abandoned"


class _MessageLog(logging.LoggerAdapter[logging.Logger]):
    def __init__(self, logger: logging.Logger, fields: Mapping[str, object]) -> None:
        super().__init__(logger, fields)
        self._fields = dict(fields)

    def with_fields(self, **fields: object) -> _MessageLog:
        return _MessageLog(self.logger, {**self._fields, **fields})

    def process(
        self, msg: object, kwargs: MutableMapping[str, Any]
    ) -> tuple[object, MutableMapping[str, Any]]:
        extra = {**self._fields, **kwargs.get("extra", {})}
        kwargs["extra"] = extra
        suffix = " ".join(f"{key}={value}" for key, value in extra.items() if value is not None)
        return f"{msg} | {suffix}", kwargs


class _IdProbe(BaseModel):
    event_id: str | None = None

def _probe_event_id(raw: bytes) -> str | None:
    try:
        event_id = _IdProbe.model_validate_json(raw).event_id
    except ValidationError:
        return None
    return event_id[:_MAX_EVENT_ID_LENGTH] if event_id is not None else None


def parse_event(raw: bytes | None) -> MeetingProcessingRequested:
    if not raw:
        raise EventError("invalid_json", "message value is empty")
    try:
        return MeetingProcessingRequested.model_validate_json(raw)
    except ValidationError as exc:
        details = exc.errors(include_input=False, include_url=False)
        text = "; ".join(
            f"{'.'.join(str(p) for p in d['loc']) or '<root>'}: {d['msg']}" for d in details
        )[:500]
        is_json_error = any(d["type"] == "json_invalid" for d in details)
        error_type = "invalid_json" if is_json_error else "invalid_event_schema"
        raise EventError(error_type, text, _probe_event_id(raw)) from exc

class MeetingConsumer:
    def __init__(
        self,
        source: MessageSource,
        pipeline: PipelineRunner,
        processed_events: ProcessedEventsLookup,
        dead_letters: DeadLetterSink,
        stop: threading.Event,
        *,
        audio_uri: Callable[[str], str],
        default_language: str | None,
        max_retries: int,
        backoff_ms: int,
        backoff_max_ms: int,
        poll_timeout_s: float = 1.0,
    ) -> None:
        self._source = source
        self._pipeline = pipeline
        self._processed_events = processed_events
        self._dead_letters = dead_letters
        self._stop = stop
        self._audio_uri = audio_uri
        self._default_language = default_language
        self._max_retries = max_retries
        self._backoff_ms = backoff_ms
        self._backoff_max_ms = backoff_max_ms
        self._poll_timeout_s = poll_timeout_s

    def run(self) -> None:
        log.info("consumer started")
        try:
            while not self._stop.is_set():
                message = self._source.poll(self._poll_timeout_s)
                if message is not None:
                    self._process(message)
        finally:
            log.info("consumer stopped")

    def _process(self, message: ConsumedMessage) -> None:
        started = time.monotonic()
        mlog = _MessageLog(
            log, {"topic": message.topic, "partition": message.partition, "offset": message.offset}
        )
        mlog.info("message received")
        try:
            disposition = self._decide(message, mlog)
        finally:
            self._source.resume()
        if disposition is not Disposition.ABANDONED:
            self._commit(message, mlog)
        mlog.info(
            "message finished",
            extra={"result": disposition.value, "duration_s": round(time.monotonic() - started, 3)},
        )

    def _decide(self, message: ConsumedMessage, mlog: _MessageLog) -> Disposition:
        try:
            event = parse_event(message.value)
        except EventError as exc:
            mlog.error(
                "message rejected: invalid event",
                extra={"error_type": exc.error_type, "error": str(exc)},
            )
            failure = Failure(FailureKind.PERMANENT, exc.error_type, str(exc))
            return self._dead_letter(
                message, exc.event_id, failure, attempts=0, exhausted=False, mlog=mlog
            )

        elog = mlog.with_fields(
            event_id=event.event_id,
            correlation_id=event.correlation_id,
            meeting_id=event.payload.meeting_id,
        )
        elog.info("message validated")
        return self._run_attempts(message, event, elog)

    def _run_attempts(
        self, message: ConsumedMessage, event: MeetingProcessingRequested, elog: _MessageLog
    ) -> Disposition:
        event_id = str(event.event_id)
        attempt = 0
        while True:
            attempt += 1
            alog = elog.with_fields(attempt=attempt)
            outcome = self._attempt(event, alog)
            if isinstance(outcome, HandlingResult):
                return Disposition.COMPLETED
            if outcome.kind is FailureKind.PERMANENT:
                return self._dead_letter(message, event_id, outcome, attempt, False, alog)
            if attempt > self._max_retries:
                return self._dead_letter(message, event_id, outcome, attempt, True, alog)

            delay_s = min(self._backoff_ms * 2 ** (attempt - 1), self._backoff_max_ms) / 1000
            alog.warning(
                "retry scheduled",
                extra={
                    "next_attempt": attempt + 1,
                    "delay_s": delay_s,
                    "error_type": outcome.error_type,
                },
            )
            if self._stop.wait(delay_s):
                alog.warning("shutdown requested during backoff; message left uncommitted")
                return Disposition.ABANDONED
            self._source.keepalive()

    def _handle(self, event: MeetingProcessingRequested, alog: _MessageLog) -> HandlingResult:
        if self._processed_events.is_processed(event.event_id):
            alog.info("event already processed, skipping pipeline")
            return HandlingResult.DUPLICATE

        job = TranscribeJob(
            job_id=str(event.event_id),
            meeting_id=str(event.payload.meeting_id),
            audio_uri=self._audio_uri(event.payload.audio_object_key),
            language=event.payload.language or self._default_language,
        )
        with recording_event(event.event_id):
            self._pipeline.run(job)
        return HandlingResult.PROCESSED

    def _attempt(self, event: MeetingProcessingRequested, alog: _MessageLog) -> HandlingResult | Failure:
        started = time.monotonic()
        alog.info("processing started")
        try:
            result = self._handle(event, alog)
        except Exception as exc: # noqa: BLE001
            failure = classify(exc)
            alog.error(
                "processing failed",
                extra={
                    "error_type": failure.error_type,
                    "failure_kind": failure.kind.value,
                    "duration_s": round(time.monotonic() - started, 3),
                },
                exc_info=exc,
            )
            return failure
        alog.info(
            "processing completed",
            extra={"result": result.value, "duration_s": round(time.monotonic() - started, 3)},
        )
        return result

    def _dead_letter(
        self,
        message: ConsumedMessage,
        event_id: str | None,
        failure: Failure,
        attempts: int,
        exhausted: bool,
        mlog: _MessageLog,
    ) -> Disposition:
        record = DeadLetter.create(
            topic=message.topic,
            partition=message.partition,
            offset=message.offset,
            value=message.value,
            event_id=event_id,
            error_type=failure.error_type,
            error_description=failure.description,
            attempts=attempts,
            retries_exhausted=exhausted,
        )
        try:
            self._dead_letters.publish(message.key, record)
        except DlqPublishError:
            mlog.critical("DLQ publish failed; source message left uncommitted")
            raise
        mlog.error(
            "message sent to DLQ",
            extra={
                "error_type": failure.error_type,
                "attempts": attempts,
                "retries_exhausted": exhausted,
            },
        )
        return Disposition.DEAD_LETTERED

    def _commit(self, message: ConsumedMessage, mlog: _MessageLog) -> None:
        try:
            self._source.commit(message)
        except CommitFailedError as exc:
            mlog.error("offset commit failed; message will be redelivered", extra={"error": str(exc)})
            return
        mlog.info("offset committed", extra={"committed_offset": message.offset + 1})
