-- Initial canonical PostgreSQL schema. Qdrant is an index for voice vectors;
-- project participants, meeting speakers, and their confirmed links live here.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_email_key UNIQUE (email),
    CONSTRAINT users_email_nonempty CHECK (btrim(email) <> ''),
    CONSTRAINT users_display_name_nonempty CHECK (btrim(display_name) <> '')
);

CREATE TABLE projects (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT NOT NULL CHECK (btrim(name) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_memberships (
    project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id    UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    role       TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'reader')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

CREATE TABLE project_participants (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    user_id      UUID REFERENCES users (id) ON DELETE SET NULL,
    display_name TEXT NOT NULL CHECK (btrim(display_name) <> ''),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, id),
    CONSTRAINT project_participants_project_user_key UNIQUE (project_id, user_id)
);

CREATE TABLE meetings (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    title      TEXT NOT NULL CHECK (btrim(title) <> ''),
    meeting_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE transcripts (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id UUID NOT NULL UNIQUE REFERENCES meetings (id) ON DELETE CASCADE,
    full_text  TEXT NOT NULL,
    language   TEXT,
    model      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- A diarized voice instance in one meeting. label is local to that meeting.
-- participant_id is only set after user confirmation; similarity search results
-- are returned by the API and are not persisted as suggestions here.
CREATE TABLE meeting_speakers (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meeting_id        UUID NOT NULL REFERENCES meetings (id) ON DELETE CASCADE,
    label             TEXT NOT NULL CHECK (btrim(label) <> ''),
    participant_id    UUID,
    speech_ms         INTEGER CHECK (speech_ms IS NULL OR speech_ms >= 0),
    qdrant_point_id   UUID UNIQUE,
    embedding_status  TEXT NOT NULL DEFAULT 'no_embedding'
        CHECK (embedding_status IN ('saved', 'no_embedding', 'insufficient_speech', 'failed')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (meeting_id, label),
    CONSTRAINT meeting_speakers_participant_fk
        FOREIGN KEY (participant_id) REFERENCES project_participants (id) ON DELETE SET NULL,
    CONSTRAINT meeting_speakers_point_iff_saved
        CHECK ((embedding_status = 'saved') = (qdrant_point_id IS NOT NULL))
);

CREATE INDEX meeting_speakers_participant_idx
    ON meeting_speakers (participant_id) WHERE participant_id IS NOT NULL;

CREATE TABLE transcript_segments (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transcript_id      UUID NOT NULL REFERENCES transcripts (id) ON DELETE CASCADE,
    meeting_speaker_id UUID REFERENCES meeting_speakers (id) ON DELETE SET NULL,
    segment_index      INTEGER NOT NULL CHECK (segment_index >= 0),
    text               TEXT NOT NULL,
    start_ms           INTEGER NOT NULL CHECK (start_ms >= 0),
    end_ms             INTEGER NOT NULL CHECK (end_ms >= start_ms),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (transcript_id, segment_index)
);

CREATE INDEX transcript_segments_speaker_idx
    ON transcript_segments (meeting_speaker_id) WHERE meeting_speaker_id IS NOT NULL;
CREATE INDEX meetings_project_date_idx ON meetings (project_id, meeting_at DESC);
CREATE INDEX project_participants_name_idx ON project_participants (project_id, display_name);

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER projects_set_updated_at BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER project_participants_set_updated_at BEFORE UPDATE ON project_participants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER meetings_set_updated_at BEFORE UPDATE ON meetings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER transcripts_set_updated_at BEFORE UPDATE ON transcripts
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER meeting_speakers_set_updated_at BEFORE UPDATE ON meeting_speakers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
