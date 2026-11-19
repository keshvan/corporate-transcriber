package repo

import (
	"context"
	"errors"
	"fmt"

	"backend/internal/entity"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type TranscriptRepository struct {
	db *pgxpool.Pool
}

func NewTranscriptRepository(db *pgxpool.Pool) *TranscriptRepository {
	return &TranscriptRepository{db: db}
}

func (r *TranscriptRepository) GetByMeetingID(
	ctx context.Context,
	meetingID string,
) (*entity.MeetingTranscript, error) {
	transcript := &entity.MeetingTranscript{
		MeetingID: meetingID,
		Speakers:  make([]entity.MeetingSpeaker, 0),
		Segments:  make([]entity.TranscriptSegment, 0),
	}
	err := r.db.QueryRow(ctx, `
		SELECT id, full_text, language, model, created_at, updated_at
		FROM transcripts
		WHERE meeting_id = $1
	`, meetingID).Scan(
		&transcript.ID,
		&transcript.FullText,
		&transcript.Language,
		&transcript.Model,
		&transcript.CreatedAt,
		&transcript.UpdatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, entity.ErrTranscriptNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("get transcript for meeting %q: %w", meetingID, err)
	}

	speakers, speakerIDs, err := r.listSpeakers(ctx, meetingID)
	if err != nil {
		return nil, err
	}
	transcript.Speakers = speakers

	rows, err := r.db.Query(ctx, `
		SELECT id, segment_index, text, start_ms, end_ms, meeting_speaker_id
		FROM transcript_segments
		WHERE transcript_id = $1
		ORDER BY segment_index
	`, transcript.ID)
	if err != nil {
		return nil, fmt.Errorf("list transcript segments for meeting %q: %w", meetingID, err)
	}
	defer rows.Close()

	for rows.Next() {
		var segment entity.TranscriptSegment
		var speakerID *string
		if err := rows.Scan(
			&segment.ID,
			&segment.SegmentIndex,
			&segment.Text,
			&segment.StartMS,
			&segment.EndMS,
			&speakerID,
		); err != nil {
			return nil, fmt.Errorf("scan transcript segment: %w", err)
		}
		segment.TranscriptID = transcript.ID
		if speakerID != nil {
			segment.Speaker = speakerIDs[*speakerID]
		}
		transcript.Segments = append(transcript.Segments, segment)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate transcript segments: %w", err)
	}
	return transcript, nil
}

func (r *TranscriptRepository) listSpeakers(
	ctx context.Context,
	meetingID string,
) ([]entity.MeetingSpeaker, map[string]*entity.MeetingSpeaker, error) {
	rows, err := r.db.Query(ctx, `
		SELECT ms.id, ms.meeting_id, ms.label, ms.participant_id, pp.display_name,
		       ms.speech_ms, ms.qdrant_point_id, ms.embedding_status, ms.created_at, ms.updated_at
		FROM meeting_speakers ms
		LEFT JOIN project_participants pp ON pp.id = ms.participant_id
		WHERE ms.meeting_id = $1
		ORDER BY ms.label
	`, meetingID)
	if err != nil {
		return nil, nil, fmt.Errorf("list speakers for meeting %q: %w", meetingID, err)
	}
	defer rows.Close()

	speakers := make([]entity.MeetingSpeaker, 0)
	byID := make(map[string]*entity.MeetingSpeaker)
	for rows.Next() {
		var speaker entity.MeetingSpeaker
		if err := rows.Scan(
			&speaker.ID,
			&speaker.MeetingID,
			&speaker.Label,
			&speaker.ParticipantID,
			&speaker.ParticipantName,
			&speaker.SpeechMS,
			&speaker.QdrantPointID,
			&speaker.EmbeddingStatus,
			&speaker.CreatedAt,
			&speaker.UpdatedAt,
		); err != nil {
			return nil, nil, fmt.Errorf("scan meeting speaker: %w", err)
		}
		speakers = append(speakers, speaker)
		byID[speaker.ID] = &speakers[len(speakers)-1]
	}
	if err := rows.Err(); err != nil {
		return nil, nil, fmt.Errorf("iterate meeting speakers: %w", err)
	}
	return speakers, byID, nil
}
