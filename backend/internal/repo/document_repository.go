package repo

import (
	"context"
	"errors"
	"fmt"

	"backend/internal/entity"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type DocumentRepository struct {
	db *pgxpool.Pool
}

func NewDocumentRepository(db *pgxpool.Pool) *DocumentRepository {
	return &DocumentRepository{db: db}
}

func (r *DocumentRepository) Create(ctx context.Context, document entity.Document) (*entity.Document, error) {
	var created entity.Document
	err := r.db.QueryRow(ctx, `
		INSERT INTO documents (
			id, project_id, title, original_filename, content_type, object_key, created_by
		)
		VALUES (
			COALESCE(NULLIF($1, '')::uuid, gen_random_uuid()), $2, $3, $4, $5, $6, $7
		)
		RETURNING id, project_id, title, original_filename, content_type, object_key,
		          size_bytes, status, uploaded_at, created_by, created_at, updated_at
	`, document.ID, document.ProjectID, document.Title, document.OriginalFilename,
		document.ContentType, document.ObjectKey, document.CreatedBy).Scan(
		&created.ID,
		&created.ProjectID,
		&created.Title,
		&created.OriginalFilename,
		&created.ContentType,
		&created.ObjectKey,
		&created.SizeBytes,
		&created.Status,
		&created.UploadedAt,
		&created.CreatedBy,
		&created.CreatedAt,
		&created.UpdatedAt,
	)
	if err != nil {
		return nil, fmt.Errorf("create document for project %q: %w", document.ProjectID, err)
	}
	return &created, nil
}

func (r *DocumentRepository) GetByProject(
	ctx context.Context,
	projectID, documentID string,
) (*entity.Document, error) {
	var document entity.Document
	err := scanDocument(r.db.QueryRow(ctx, `
		SELECT id, project_id, title, original_filename, content_type, object_key,
		       size_bytes, status, uploaded_at, created_by, created_at, updated_at
		FROM documents
		WHERE project_id = $1 AND id = $2
	`, projectID, documentID), &document)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, entity.ErrDocumentNotFound
	}
	if err != nil {
		return nil, fmt.Errorf("get document %q in project %q: %w", documentID, projectID, err)
	}
	return &document, nil
}

func (r *DocumentRepository) ListByProject(ctx context.Context, projectID string) ([]entity.Document, error) {
	rows, err := r.db.Query(ctx, `
		SELECT id, project_id, title, original_filename, content_type, object_key,
		       size_bytes, status, uploaded_at, created_by, created_at, updated_at
		FROM documents
		WHERE project_id = $1
		ORDER BY created_at DESC, id DESC
	`, projectID)
	if err != nil {
		return nil, fmt.Errorf("list documents for project %q: %w", projectID, err)
	}
	defer rows.Close()

	documents := make([]entity.Document, 0)
	for rows.Next() {
		var document entity.Document
		if err := scanDocument(rows, &document); err != nil {
			return nil, fmt.Errorf("scan document: %w", err)
		}
		documents = append(documents, document)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate documents for project %q: %w", projectID, err)
	}
	return documents, nil
}

// MarkUploadComplete records the verified object size and queues document
// processing. The caller should publish the processing event after this update.
func (r *DocumentRepository) MarkUploadComplete(
	ctx context.Context,
	projectID, documentID string,
	sizeBytes int64,
) (*entity.Document, error) {
	var document entity.Document
	err := scanDocument(r.db.QueryRow(ctx, `
		UPDATE documents
		SET size_bytes = $3, status = 'queued', uploaded_at = now()
		WHERE project_id = $1 AND id = $2 AND status = 'awaiting_upload'
		RETURNING id, project_id, title, original_filename, content_type, object_key,
		          size_bytes, status, uploaded_at, created_by, created_at, updated_at
	`, projectID, documentID, sizeBytes), &document)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, entity.ErrDocumentUploadNotPending
	}
	if err != nil {
		return nil, fmt.Errorf("complete upload for document %q in project %q: %w", documentID, projectID, err)
	}
	return &document, nil
}

func (r *DocumentRepository) UpdateStatus(
	ctx context.Context,
	projectID, documentID, status string,
) error {
	result, err := r.db.Exec(ctx, `
		UPDATE documents
		SET status = $3
		WHERE project_id = $1 AND id = $2
	`, projectID, documentID, status)
	if err != nil {
		return fmt.Errorf("update status for document %q: %w", documentID, err)
	}
	if result.RowsAffected() == 0 {
		return entity.ErrDocumentNotFound
	}
	return nil
}

func scanDocument(row pgx.Row, document *entity.Document) error {
	return row.Scan(
		&document.ID,
		&document.ProjectID,
		&document.Title,
		&document.OriginalFilename,
		&document.ContentType,
		&document.ObjectKey,
		&document.SizeBytes,
		&document.Status,
		&document.UploadedAt,
		&document.CreatedBy,
		&document.CreatedAt,
		&document.UpdatedAt,
	)
}
