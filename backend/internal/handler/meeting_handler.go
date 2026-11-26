package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"time"

	"backend/internal/entity"
	"backend/internal/service"

	"github.com/go-chi/chi/v5"
)

type MeetingService interface {
	ListMeetings(ctx context.Context) ([]entity.Meeting, error)
	GetTranscript(ctx context.Context, meetingID string) (*entity.MeetingTranscript, error)
	InitializeUpload(ctx context.Context, input service.InitMeetingUploadInput) (*service.MeetingUploadInitialization, error)
	ConfirmUpload(ctx context.Context, projectID, meetingID string) (*entity.Meeting, error)
}

type MeetingHandler struct {
	service MeetingService
}

func NewMeetingHandler(meetingService MeetingService) *MeetingHandler {
	return &MeetingHandler{service: meetingService}
}

func (h *MeetingHandler) RegisterRoutes(router chi.Router) {
	router.Get("/meetings", h.ListMeetings)
	router.Get("/meetings/{meetingID}/transcript", h.GetTranscript)
	router.Post("/projects/{projectID}/meetings/uploads", h.InitializeUpload)
	router.Post("/projects/{projectID}/meetings/{meetingID}/uploads/complete", h.ConfirmUpload)
}

func (h *MeetingHandler) InitializeUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	if !uuidPattern.MatchString(projectID) {
		writeError(w, http.StatusBadRequest, "projectID must be a UUID")
		return
	}

	var request struct {
		Title       string     `json:"title"`
		MeetingAt   *time.Time `json:"meeting_at"`
		Filename    string     `json:"filename"`
		ContentType string     `json:"content_type"`
	}
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON request body")
		return
	}

	result, err := h.service.InitializeUpload(r.Context(), service.InitMeetingUploadInput{
		ProjectID:   projectID,
		Title:       request.Title,
		MeetingAt:   request.MeetingAt,
		Filename:    request.Filename,
		ContentType: request.ContentType,
	})
	if errors.Is(err, service.ErrInvalidUploadInput) {
		writeError(w, http.StatusBadRequest, "title, filename and content_type are required")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not initialize meeting upload")
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (h *MeetingHandler) ConfirmUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	meetingID := chi.URLParam(r, "meetingID")
	if !uuidPattern.MatchString(projectID) {
		writeError(w, http.StatusBadRequest, "projectID must be a UUID")
		return
	}
	if !uuidPattern.MatchString(meetingID) {
		writeError(w, http.StatusBadRequest, "meetingID must be a UUID")
		return
	}

	meeting, err := h.service.ConfirmUpload(r.Context(), projectID, meetingID)
	if errors.Is(err, entity.ErrMeetingNotFound) {
		writeError(w, http.StatusNotFound, "meeting not found in project")
		return
	}
	if errors.Is(err, entity.ErrMeetingUploadNotPending) {
		writeError(w, http.StatusConflict, "meeting upload is not pending")
		return
	}
	if errors.Is(err, service.ErrUploadedObjectMissing) {
		writeError(w, http.StatusConflict, "uploaded object is not present in storage")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not confirm meeting upload")
		return
	}
	writeJSON(w, http.StatusOK, meeting)
}

func (h *MeetingHandler) ListMeetings(w http.ResponseWriter, r *http.Request) {
	meetings, err := h.service.ListMeetings(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not load meetings")
		return
	}
	writeJSON(w, http.StatusOK, meetings)
}

var uuidPattern = regexp.MustCompile(`^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$`)

func (h *MeetingHandler) GetTranscript(w http.ResponseWriter, r *http.Request) {
	meetingID := chi.URLParam(r, "meetingID")
	if !uuidPattern.MatchString(meetingID) {
		writeError(w, http.StatusBadRequest, "meetingID must be a UUID")
		return
	}

	transcript, err := h.service.GetTranscript(r.Context(), meetingID)
	if errors.Is(err, service.ErrTranscriptNotFound) {
		writeError(w, http.StatusNotFound, "transcript not found")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not load transcript")
		return
	}
	writeJSON(w, http.StatusOK, transcript)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}
