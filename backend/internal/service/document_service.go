package service

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"backend/internal/entity"
)

type DocumentRepository interface {
	Create(ctx context.Context, document entity.Document) (*entity.Document, error)
	GetByProject(ctx context.Context, projectID, documentID string) (*entity.Document, error)
	MarkUploadComplete(ctx context.Context, projectID, documentID string, sizeBytes int64) (*entity.Document, error)
}

type InitDocumentUploadInput struct {
	ProjectID        string
	CreatedBy        *string
	Title            string
	OriginalFilename string
	ContentType      string
}

type DocumentUploadInitialization struct {
	Document entity.Document `json:"document"`
	Upload   PresignedUpload `json:"upload"`
}

type DocumentService struct {
	documents DocumentRepository
	storage   ObjectStorage
}

func NewDocumentService(documents DocumentRepository, storage ObjectStorage) *DocumentService {
	return &DocumentService{documents: documents, storage: storage}
}

func (s *DocumentService) InitializeUpload(
	ctx context.Context,
	input InitDocumentUploadInput,
) (*DocumentUploadInitialization, error) {
	input.ProjectID = strings.TrimSpace(input.ProjectID)
	input.Title = strings.TrimSpace(input.Title)
	input.OriginalFilename = strings.TrimSpace(input.OriginalFilename)
	input.ContentType = strings.TrimSpace(input.ContentType)
	if input.ProjectID == "" || input.Title == "" || input.OriginalFilename == "" || input.ContentType == "" {
		return nil, ErrInvalidUploadInput
	}

	documentID, err := newUUID()
	if err != nil {
		return nil, err
	}
	objectKey := s.storage.BuildDocumentObjectKey(input.ProjectID, documentID, input.OriginalFilename)
	upload, err := createPresignedUpload(ctx, s.storage, objectKey, input.ContentType)
	if err != nil {
		return nil, err
	}

	document, err := s.documents.Create(ctx, entity.Document{
		ID:               documentID,
		ProjectID:        input.ProjectID,
		Title:            input.Title,
		OriginalFilename: input.OriginalFilename,
		ContentType:      input.ContentType,
		ObjectKey:        objectKey,
		CreatedBy:        input.CreatedBy,
	})
	if err != nil {
		return nil, fmt.Errorf("save pending document upload: %w", err)
	}
	return &DocumentUploadInitialization{Document: *document, Upload: upload}, nil
}

func (s *DocumentService) ConfirmUpload(
	ctx context.Context,
	projectID, documentID string,
) (*entity.Document, error) {
	document, err := s.documents.GetByProject(ctx, projectID, documentID)
	if err != nil {
		return nil, err
	}
	if document.Status != "awaiting_upload" {
		if document.UploadedAt != nil {
			return document, nil
		}
		return nil, entity.ErrDocumentUploadNotPending
	}

	sizeBytes, exists, err := s.storage.HeadObject(ctx, document.ObjectKey)
	if err != nil {
		return nil, fmt.Errorf("verify uploaded document %q: %w", documentID, err)
	}
	if !exists {
		return nil, ErrUploadedObjectMissing
	}

	completed, err := s.documents.MarkUploadComplete(ctx, projectID, documentID, sizeBytes)
	if errors.Is(err, entity.ErrDocumentUploadNotPending) {
		// A concurrent confirmation may have completed the same upload.
		current, getErr := s.documents.GetByProject(ctx, projectID, documentID)
		if getErr == nil && current.UploadedAt != nil {
			return current, nil
		}
	}
	if err != nil {
		return nil, fmt.Errorf("confirm document upload %q: %w", documentID, err)
	}
	return completed, nil
}
