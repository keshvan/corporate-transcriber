package repo

import (
	"context"
	"errors"
	"fmt"
	"time"

	"backend/internal/entity"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type MeetingRepository struct {
	db *pgxpool.Pool
}

func NewMeetingRepository(db *pgxpool.Pool) *MeetingRepository {
	return &MeetingRepository{db: db}
}

func (r *MeetingRepository) List(ctx context.Context) ([]entity.Meeting, error) {
	rows, err := r.db.Query(ctx, `
		SELECT id, project_id, title, meeting_at, source_object_key, source_filename,
		       source_content_type, source_size_bytes, upload_status, processing_status,
		       source_uploaded_at, created_at
		FROM meetings
		ORDER BY created_at DESC, id DESC
	`)
	if err != nil {
		return nil, fmt.Errorf("list meetings: %w", err)
	}
	defer rows.Close()

	meetings := make([]entity.Meeting, 0)
	for rows.Next() {
		var meeting entity.Meeting
		if err := scanMeeting(rows, &meeting); err != nil {
			return nil, fmt.Errorf("scan meeting: %w", err)
		}
		meetings = append(meetings, meeting)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate meetings: %w", err)
	}
	return meetings, nil
}

func (r *MeetingRepository) ListByProject(ctx context.Context, projectID string) ([]entity.Meeting, error) {
	rows, err := r.db.Query(ctx, `
		SELECT id, project_id, title, meeting_at, source_object_key, source_filename,
		       source_content_type, source_size_bytes, upload_status, processing_status,
		       source_uploaded_at, created_at
		FROM meetings
		WHERE project_id = $1
		ORDER BY created_at DESC, id DESC
	`, projectID)
	if err != nil {
		return nil, fmt.Errorf("list meetings for project %q: %w", projectID, err)
	}
	defer rows.Close()

	meetings := make([]entity.Meeting, 0)
	for rows.Next() {
		var meeting entity.Meeting
		if err := scanMeeting(rows, &meeting); err != nil {
			return nil, fmt.Errorf("scan meeting: %w", err)
		}
		meetings = append(meetings, meeting)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate meetings for project %q: %w", projectID, err)
	}
	return meetings, nil
}

func (r *MeetingRepository) GetByProject(
	ctx context.Context,
	projectID, meetingID string,
) (*entity.Meeting, error) {
	var meeting entity.Meeting
	err := scanMeeting(r.db.QueryRow(ctx, `
		SELECT id, project_id, title, meeting_at, source_object_key, source_filename,
		       source_content_type, source_size_bytes, upload_status, processing_status,
		       source_uploaded_at, created_at
		FROM meetings
		WHERE project_id = $1 AND id = $2
	`, projectID, meetingID), &meeting)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, entity.ErrMeetingNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("get meeting %q in project %q: %w", meetingID, projectID, err)
	}
	return &meeting, nil
}

func (r *MeetingRepository) CreateForUpload(
	ctx context.Context,
	meetingID, projectID, title string,
	meetingAt *time.Time,
	sourceObjectKey, sourceFilename, sourceContentType string,
) (*entity.Meeting, error) {
	var meeting entity.Meeting
	err := r.db.QueryRow(ctx, `
		INSERT INTO meetings (
			id, project_id, title, meeting_at, source_object_key, source_filename,
			source_content_type, upload_status
		)
		VALUES ($1, $2, $3, $4, $5, $6, $7, 'awaiting_upload')
		RETURNING id, project_id, title, meeting_at, source_object_key, source_filename,
		          source_content_type, source_size_bytes, upload_status, processing_status,
		          source_uploaded_at, created_at
	`, meetingID, projectID, title, meetingAt, sourceObjectKey, sourceFilename, sourceContentType).Scan(
		&meeting.ID,
		&meeting.ProjectID,
		&meeting.Title,
		&meeting.MeetingAt,
		&meeting.SourceObjectKey,
		&meeting.SourceFilename,
		&meeting.SourceContentType,
		&meeting.SourceSizeBytes,
		&meeting.UploadStatus,
		&meeting.ProcessingStatus,
		&meeting.SourceUploadedAt,
		&meeting.CreatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("create meeting upload %q for project %q: %w", meetingID, projectID, err)
	}
	return &meeting, nil
}

// MarkUploadComplete transitions a meeting whose object was verified in
// object storage into the queued state before the processing event is published.
func (r *MeetingRepository) MarkUploadComplete(
	ctx context.Context,
	projectID, meetingID string,
	sizeBytes int64,
) (*entity.Meeting, error) {
	var meeting entity.Meeting
	err := r.db.QueryRow(ctx, `
		UPDATE meetings
		SET upload_status = 'uploaded',
		    processing_status = 'queued',
		    source_size_bytes = $3,
		    source_uploaded_at = now()
		WHERE project_id = $1 AND id = $2 AND upload_status = 'awaiting_upload'
		RETURNING id, project_id, title, meeting_at, source_object_key, source_filename,
		          source_content_type, source_size_bytes, upload_status, processing_status,
		          source_uploaded_at, created_at
	`, projectID, meetingID, sizeBytes).Scan(
		&meeting.ID,
		&meeting.ProjectID,
		&meeting.Title,
		&meeting.MeetingAt,
		&meeting.SourceObjectKey,
		&meeting.SourceFilename,
		&meeting.SourceContentType,
		&meeting.SourceSizeBytes,
		&meeting.UploadStatus,
		&meeting.ProcessingStatus,
		&meeting.SourceUploadedAt,
		&meeting.CreatedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, entity.ErrMeetingUploadNotPending
	}
	if err != nil {
		return nil, fmt.Errorf("complete upload for meeting %q in project %q: %w", meetingID, projectID, err)
	}
	return &meeting, nil
}

func (r *MeetingRepository) UpdateProcessingStatus(
	ctx context.Context,
	projectID, meetingID, status string,
) error {
	result, err := r.db.Exec(ctx, `
		UPDATE meetings
		SET processing_status = $3
		WHERE project_id = $1 AND id = $2
	`, projectID, meetingID, status)
	if err != nil {
		return fmt.Errorf("update processing status for meeting %q: %w", meetingID, err)
	}
	if result.RowsAffected() == 0 {
		return entity.ErrMeetingNotFound
	}
	return nil
}

func scanMeeting(row pgx.Row, meeting *entity.Meeting) error {
	return row.Scan(
		&meeting.ID,
		&meeting.ProjectID,
		&meeting.Title,
		&meeting.MeetingAt,
		&meeting.SourceObjectKey,
		&meeting.SourceFilename,
		&meeting.SourceContentType,
		&meeting.SourceSizeBytes,
		&meeting.UploadStatus,
		&meeting.ProcessingStatus,
		&meeting.SourceUploadedAt,
		&meeting.CreatedAt,
	)
}
