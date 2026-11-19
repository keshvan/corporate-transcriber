package service

import (
	"context"
	"errors"

	"backend/internal/entity"
)

var ErrTranscriptNotFound = errors.New("meeting transcript not found")

type MeetingRepository interface {
	List(ctx context.Context) ([]entity.Meeting, error)
}

type TranscriptRepository interface {
	GetByMeetingID(ctx context.Context, meetingID string) (*entity.MeetingTranscript, error)
}

type MeetingService struct {
	meetings    MeetingRepository
	transcripts TranscriptRepository
}

func NewMeetingService(meetings MeetingRepository, transcripts TranscriptRepository) *MeetingService {
	return &MeetingService{
		meetings:    meetings,
		transcripts: transcripts,
	}
}

func (s *MeetingService) ListMeetings(ctx context.Context) ([]entity.Meeting, error) {
	return s.meetings.List(ctx)
}

func (s *MeetingService) GetTranscript(ctx context.Context, meetingID string) (*entity.MeetingTranscript, error) {
	transcript, err := s.transcripts.GetByMeetingID(ctx, meetingID)
	if errors.Is(err, entity.ErrTranscriptNotFound) {
		return nil, ErrTranscriptNotFound
	}
	return transcript, err
}
