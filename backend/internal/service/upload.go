package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
)

var (
	ErrInvalidUploadInput    = errors.New("invalid upload input")
	ErrUploadedObjectMissing = errors.New("uploaded object was not found in object storage")
)

type ObjectStorage interface {
	PresignPut(ctx context.Context, objectKey, contentType string) (string, map[string]string, int32, error)
	HeadObject(ctx context.Context, objectKey string) (sizeBytes int64, exists bool, err error)
	BuildDocumentObjectKey(projectID, documentID, fileName string) string
	BuildMeetingObjectKey(projectID, meetingID, fileName string) string
}

type PresignedUpload struct {
	URL              string            `json:"url"`
	Method           string            `json:"method"`
	Headers          map[string]string `json:"headers"`
	ExpiresInSeconds int32             `json:"expires_in_seconds"`
}

func createPresignedUpload(
	ctx context.Context,
	storage ObjectStorage,
	objectKey, contentType string,
) (PresignedUpload, error) {
	url, headers, expiresIn, err := storage.PresignPut(ctx, objectKey, contentType)
	if err != nil {
		return PresignedUpload{}, fmt.Errorf("create presigned upload URL: %w", err)
	}
	return PresignedUpload{
		URL:              url,
		Method:           "PUT",
		Headers:          headers,
		ExpiresInSeconds: expiresIn,
	}, nil
}

func newUUID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("generate upload ID: %w", err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	encoded := hex.EncodeToString(value)
	return encoded[:8] + "-" + encoded[8:12] + "-" + encoded[12:16] + "-" + encoded[16:20] + "-" + encoded[20:], nil
}
