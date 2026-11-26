package service

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"backend/internal/entity"
)

var ErrTranscriptNotFound = errors.New("meeting transcript not found")

type MeetingRepository interface {
	List(ctx context.Context) ([]entity.Meeting, error)
	CreateForUpload(
		ctx context.Context,
		meetingID, projectID, title string,
		meetingAt *time.Time,
		sourceObjectKey, sourceFilename, sourceContentType string,
	) (*entity.Meeting, error)
	GetByProject(ctx context.Context, projectID, meetingID string) (*entity.Meeting, error)
	MarkUploadComplete(ctx context.Context, projectID, meetingID string, sizeBytes int64) (*entity.Meeting, error)
	UpdateProcessingStatus(ctx context.Context, projectID, meetingID, status string) error
}

type TranscriptRepository interface {
	GetByMeetingID(ctx context.Context, meetingID string) (*entity.MeetingTranscript, error)
}

type MeetingProcessingPublisher interface {
	PublishMeetingProcessingRequest(ctx context.Context, meetingID, audioObjectKey string) error
}

type MeetingService struct {
	meetings    MeetingRepository
	transcripts TranscriptRepository
	storage     ObjectStorage
	publisher   MeetingProcessingPublisher
}

type InitMeetingUploadInput struct {
	ProjectID   string
	Title       string
	MeetingAt   *time.Time
	Filename    string
	ContentType string
}

type MeetingUploadInitialization struct {
	Meeting entity.Meeting  `json:"meeting"`
	Upload  PresignedUpload `json:"upload"`
}

func NewMeetingService(
	meetings MeetingRepository,
	transcripts TranscriptRepository,
	storage ObjectStorage,
	publisher MeetingProcessingPublisher,
) *MeetingService {
	return &MeetingService{
		meetings:    meetings,
		transcripts: transcripts,
		storage:     storage,
		publisher:   publisher,
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

func (s *MeetingService) InitializeUpload(
	ctx context.Context,
	input InitMeetingUploadInput,
) (*MeetingUploadInitialization, error) {
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.Title = strings.TrimSpace(input.Title)
	input.Filename = strings.TrimSpace(input.Filename)
	input.ContentType = strings.TrimSpace(input.ContentType)
	if input.ProjectID == "" || input.Title == "" || input.Filename == "" || input.ContentType == "" {
		return nil, ErrInvalidUploadInput
	}

	meetingID, err := newUUID()
	if err != nil {
		return nil, err
	}
	objectKey := s.storage.BuildMeetingObjectKey(input.ProjectID, meetingID, input.Filename)
	upload, err := createPresignedUpload(ctx, s.storage, objectKey, input.ContentType)
	if err != nil {
		return nil, err
	}

	meeting, err := s.meetings.CreateForUpload(
		ctx,
		meetingID,
		input.ProjectID,
		input.Title,
		input.MeetingAt,
		objectKey,
		input.Filename,
		input.ContentType,
	)
	if err != nil {
		return nil, fmt.Errorf("save pending meeting upload: %w", err)
	}
	return &MeetingUploadInitialization{Meeting: *meeting, Upload: upload}, nil
}

func (s *MeetingService) ConfirmUpload(
	ctx context.Context,
	projectID, meetingID string,
) (*entity.Meeting, error) {
	meeting, err := s.meetings.GetByProject(ctx, projectID, meetingID)
	if err != nil {
		return nil, err
	}
	if meeting.UploadStatus != "awaiting_upload" {
		if meeting.UploadStatus == "uploaded" {
			if err := s.publishProcessing(ctx, meeting); err != nil {
				return nil, fmt.Errorf("publish processing event for meeting %q: %w", meetingID, err)
			}
			return meeting, nil
		}
		return nil, entity.ErrMeetingUploadNotPending
	}

	if meeting.SourceObjectKey == nil {
		return nil, fmt.Errorf("meeting %q has no source object key", meetingID)
	}
	sizeBytes, exists, err := s.storage.HeadObject(ctx, *meeting.SourceObjectKey)
	if err != nil {
		return nil, fmt.Errorf("verify uploaded meeting %q: %w", meetingID, err)
	}
	if !exists {
		return nil, ErrUploadedObjectMissing
	}

	completed, err := s.meetings.MarkUploadComplete(ctx, projectID, meetingID, sizeBytes)
	if errors.Is(err, entity.ErrMeetingUploadNotPending) {
		// A concurrent confirmation may have completed the same upload.
		current, getErr := s.meetings.GetByProject(ctx, projectID, meetingID)
		if getErr == nil && current.UploadStatus == "uploaded" {
			completed = current
			err = nil
		}
	}
	if err != nil {
		return nil, fmt.Errorf("confirm meeting upload %q: %w", meetingID, err)
	}
	if err := s.publishProcessing(ctx, completed); err != nil {
		return nil, fmt.Errorf("publish processing event for meeting %q: %w", meetingID, err)
	}
	return completed, nil
}

func (s *MeetingService) publishProcessing(ctx context.Context, meeting *entity.Meeting) error {
	if meeting.SourceObjectKey == nil {
		return fmt.Errorf("meeting %q has no source object key", meeting.ID)
	}
	if s.publisher == nil {
		return errors.New("meeting processing publisher is not configured")
	}
	return s.publisher.PublishMeetingProcessingRequest(ctx, meeting.ID, *meeting.SourceObjectKey)
}
