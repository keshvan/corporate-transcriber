package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"regexp"

	"backend/internal/entity"
	"backend/internal/service"

	"github.com/go-chi/chi/v5"
)

type MeetingService interface {
	ListMeetings(ctx context.Context) ([]entity.Meeting, error)
	GetTranscript(ctx context.Context, meetingID string) (*entity.MeetingTranscript, error)
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
