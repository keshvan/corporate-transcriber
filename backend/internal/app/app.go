package app

import (
	"context"
	"fmt"
	"log/slog"
	"strings"

	"backend/internal/config"
	"backend/internal/database"
	"backend/internal/handler"
	kafkabus "backend/internal/kafka"
	"backend/internal/repo"
	"backend/internal/service"
	"backend/internal/storage"
	"backend/internal/transport"

	"github.com/jackc/pgx/v5/pgxpool"
)

type App struct {
	db              *pgxpool.Pool
	httpServer      *transport.HTTPServer
	meetingProducer *kafkabus.Producer
}

func New(cfg *config.Config, log *slog.Logger) (*App, error) {
	if log == nil {
		log = slog.Default()
	}

	db, err := database.NewPostgresPool(context.Background(), cfg.Postgres.DSN(), database.DBOptions{}, log)
	if err != nil {
		return nil, fmt.Errorf("initialize postgres: %w", err)
	}

	objectStorage, err := storage.NewS3Client(context.Background(), &cfg.S3)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("initialize object storage: %w", err)
	}

	brokers := strings.Split(cfg.Kafka.KafkaBrokers, ",")
	meetingProducer, err := kafkabus.NewProducer(brokers, cfg.Kafka.KafkaTopic, log)
	if err != nil {
		db.Close()
		return nil, fmt.Errorf("initialize Kafka producer: %w", err)
	}

	meetingRepository := repo.NewMeetingRepository(db)
	transcriptRepository := repo.NewTranscriptRepository(db)
	meetingService := service.NewMeetingService(meetingRepository, transcriptRepository, objectStorage, meetingProducer)
	meetingHandler := handler.NewMeetingHandler(meetingService)
	documentRepository := repo.NewDocumentRepository(db)
	documentService := service.NewDocumentService(documentRepository, objectStorage)
	documentHandler := handler.NewDocumentHandler(documentService)
	router := transport.NewRouter(meetingHandler, documentHandler)
	httpServer := transport.NewHTTPServer(cfg.HTTP.Host, cfg.HTTP.Port, router, log)

	return &App{
		db:              db,
		httpServer:      httpServer,
		meetingProducer: meetingProducer,
	}, nil
}

func (a *App) Run(ctx context.Context) error {
	return a.httpServer.Run(ctx)
}

func (a *App) Close() {
	if a.meetingProducer != nil {
		if err := a.meetingProducer.Close(); err != nil {
			// Shutdown is best effort; the producer has already been stopped by the time
			// Close returns an error.
			slog.Error("close Kafka producer", "err", err)
		}
	}
	a.db.Close()
}
