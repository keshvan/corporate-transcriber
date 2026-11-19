package repo

import (
	"context"
	"fmt"

	"backend/internal/entity"

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
		SELECT id, project_id, title, meeting_at, created_at
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
		if err := rows.Scan(&meeting.ID, &meeting.ProjectID, &meeting.Title, &meeting.MeetingAt, &meeting.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan meeting: %w", err)
		}
		meetings = append(meetings, meeting)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate meetings: %w", err)
	}
	return meetings, nil
}
