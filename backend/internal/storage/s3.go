package storage

import (
	"backend/internal/config"
	"context"
	"errors"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awscfg "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/aws/smithy-go"
	smithyhttp "github.com/aws/smithy-go/transport/http"
)

type S3Client struct {
	client    *s3.Client
	presigner *s3.PresignClient
	bucket    string
	ttl       time.Duration
}

func NewS3Client(ctx context.Context, cfg *config.S3Config) (*S3Client, error) {
	awsCfg, err := awscfg.LoadDefaultConfig(
		ctx,
		awscfg.WithRegion(cfg.S3Region),
		awscfg.WithCredentialsProvider(
			credentials.NewStaticCredentialsProvider(cfg.S3AccessKey, cfg.S3SecretKey, ""),
		),
	)
	if err != nil {
		return nil, err
	}

	client := s3.NewFromConfig(awsCfg, func(o *s3.Options) {
		o.BaseEndpoint = aws.String(cfg.S3Endpoint)
		o.UsePathStyle = true
	})

	return &S3Client{
		client:    client,
		presigner: s3.NewPresignClient(client),
		bucket:    cfg.S3Bucket,
		ttl:       time.Duration(cfg.S3PresignTTLSecond) * time.Second,
	}, nil
}

func (s *S3Client) HeadObject(ctx context.Context, objectKey string) (int64, bool, error) {
	result, err := s.client.HeadObject(ctx, &s3.HeadObjectInput{
		Bucket: aws.String(s.bucket),
		Key:    aws.String(objectKey),
	})
	if err != nil {
		var apiErr smithy.APIError
		if errors.As(err, &apiErr) && (apiErr.ErrorCode() == "NoSuchKey" || apiErr.ErrorCode() == "NotFound") {
			return 0, false, nil
		}
		var responseErr *smithyhttp.ResponseError
		if errors.As(err, &responseErr) && responseErr.HTTPStatusCode() == http.StatusNotFound {
			return 0, false, nil
		}
		return 0, false, fmt.Errorf("head S3 object %q: %w", objectKey, err)
	}
	if result.ContentLength == nil {
		return 0, true, nil
	}
	return *result.ContentLength, true, nil
}

func (s *S3Client) PresignPut(ctx context.Context, objectKey, contentType string) (string, map[string]string, int32, error) {
	out, err := s.presigner.PresignPutObject(
		ctx,
		&s3.PutObjectInput{
			Bucket:      aws.String(s.bucket),
			Key:         aws.String(objectKey),
			ContentType: aws.String(contentType),
		},
		s3.WithPresignExpires(s.ttl),
	)
	if err != nil {
		return "", nil, 0, err
	}

	return out.URL, map[string]string{"Content-Type": contentType}, int32(s.ttl.Seconds()), nil
}

func (s *S3Client) BuildDocumentObjectKey(projectId, documentId, fileName string) string {
	ext := strings.ToLower(filepath.Ext(fileName))
	if ext == "" {
		ext = ".bin"
	}
	return fmt.Sprintf("%s/documents/%s/source%s", projectId, documentId, ext)
}

func (s *S3Client) BuildMeetingObjectKey(projectId, documentId, fileName string) string {
	ext := strings.ToLower(filepath.Ext(fileName))
	if ext == "" {
		ext = ".bin"
	}
	return fmt.Sprintf("%s/meetings/%s/source%s", projectId, documentId, ext)
}
