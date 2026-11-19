package app

import (
	"context"
	"fmt"
	"log/slog"

	"backend/internal/config"
	"backend/internal/database"
	"backend/internal/handler"
	"backend/internal/repo"
	"backend/internal/service"
	"backend/internal/transport"

	"github.com/jackc/pgx/v5/pgxpool"
)

type App struct {
	db         *pgxpool.Pool
	httpServer *transport.HTTPServer
}

func New(cfg *config.Config, log *slog.Logger) (*App, error) {
	if log == nil {
		log = slog.Default()
	}

	db, err := database.NewPostgresPool(context.Background(), cfg.Postgres.DSN(), database.DBOptions{}, log)
	if err != nil {
		return nil, fmt.Errorf("initialize postgres: %w", err)
	}

	meetingRepository := repo.NewMeetingRepository(db)
	transcriptRepository := repo.NewTranscriptRepository(db)
	meetingService := service.NewMeetingService(meetingRepository, transcriptRepository)
	meetingHandler := handler.NewMeetingHandler(meetingService)
	router := transport.NewRouter(meetingHandler)
	httpServer := transport.NewHTTPServer(cfg.HTTP.Host, cfg.HTTP.Port, router, log)

	return &App{
		db:         db,
		httpServer: httpServer,
	}, nil
}

func (a *App) Run(ctx context.Context) error {
	return a.httpServer.Run(ctx)
}

func (a *App) Close() {
	a.db.Close()
}
