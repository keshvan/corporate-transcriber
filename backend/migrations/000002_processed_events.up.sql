-- Durable idempotency records for worker events. The worker writes this row
-- in the same transaction as the transcript result.
CREATE TABLE processed_events (
    event_id     UUID PRIMARY KEY,
    meeting_id   UUID NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX processed_events_meeting_id_idx ON processed_events (meeting_id);
