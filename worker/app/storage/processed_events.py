from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from uuid import UUID

from psycopg import Connection
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool

_IS_PROCESSED = "SELECT 1 FROM processed_events WHERE event_id = %s"

_MARK_PROCESSED = """
INSERT INTO processed_events (event_id, meeting_id)
VALUES (%s, %s)
ON CONFLICT (event_id) DO NOTHING
"""

_current_event_id: ContextVar[UUID | None] = ContextVar("current_event_id", default=None)

@contextmanager
def recording_event(event_id: UUID) -> Iterator[None]:
    token = _current_event_id.set(event_id)
    try:
        yield
    finally:
        _current_event_id.reset(token)

def record_current_event(conn: Connection[TupleRow], meeting_id: UUID) -> None:
    event_id = _current_event_id.get()
    if event_id is not None:
        conn.execute(_MARK_PROCESSED, (event_id, meeting_id))

class ProcessedEvents:
    def __init__(self, pool: ConnectionPool[Connection[TupleRow]]) -> None:
        self._pool = pool

    def is_processed(self, event_id: UUID) -> bool:
        with self._pool.connection() as conn:
            return conn.execute(_IS_PROCESSED, (event_id,)).fetchone() is not None
