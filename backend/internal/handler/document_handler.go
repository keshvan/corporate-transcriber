package handler

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	"backend/internal/entity"
	"backend/internal/service"

	"github.com/go-chi/chi/v5"
)

type DocumentService interface {
	InitializeUpload(ctx context.Context, input service.InitDocumentUploadInput) (*service.DocumentUploadInitialization, error)
	ConfirmUpload(ctx context.Context, projectID, documentID string) (*entity.Document, error)
}

type DocumentHandler struct {
	service DocumentService
}

func NewDocumentHandler(documentService DocumentService) *DocumentHandler {
	return &DocumentHandler{service: documentService}
}

func (h *DocumentHandler) RegisterRoutes(router chi.Router) {
	router.Post("/projects/{projectID}/documents/uploads", h.InitializeUpload)
	router.Post("/projects/{projectID}/documents/{documentID}/uploads/complete", h.ConfirmUpload)
}

func (h *DocumentHandler) InitializeUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	if !uuidPattern.MatchString(projectID) {
		writeError(w, http.StatusBadRequest, "projectID must be a UUID")
		return
	}

	var request struct {
		Title       string `json:"title"`
		Filename    string `json:"filename"`
		ContentType string `json:"content_type"`
	}
	if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON request body")
		return
	}

	result, err := h.service.InitializeUpload(r.Context(), service.InitDocumentUploadInput{
		ProjectID:        projectID,
		Title:            request.Title,
		OriginalFilename: request.Filename,
		ContentType:      request.ContentType,
	})
	if errors.Is(err, service.ErrInvalidUploadInput) {
		writeError(w, http.StatusBadRequest, "title, filename and content_type are required")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not initialize document upload")
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func (h *DocumentHandler) ConfirmUpload(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "projectID")
	documentID := chi.URLParam(r, "documentID")
	if !uuidPattern.MatchString(projectID) {
		writeError(w, http.StatusBadRequest, "projectID must be a UUID")
		return
	}
	if !uuidPattern.MatchString(documentID) {
		writeError(w, http.StatusBadRequest, "documentID must be a UUID")
		return
	}

	document, err := h.service.ConfirmUpload(r.Context(), projectID, documentID)
	if errors.Is(err, entity.ErrDocumentNotFound) {
		writeError(w, http.StatusNotFound, "document not found in project")
		return
	}
	if errors.Is(err, entity.ErrDocumentUploadNotPending) {
		writeError(w, http.StatusConflict, "document upload is not pending")
		return
	}
	if errors.Is(err, service.ErrUploadedObjectMissing) {
		writeError(w, http.StatusConflict, "uploaded object is not present in storage")
		return
	}
	if err != nil {
		writeError(w, http.StatusInternalServerError, "could not confirm document upload")
		return
	}
	writeJSON(w, http.StatusOK, document)
}
