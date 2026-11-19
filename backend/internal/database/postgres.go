package database

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type DBOptions struct {
	MaxRetries     int
	RetryInterval  time.Duration
	MaxConnections int32
}

func (o *DBOptions) setDefaults() {
	if o.MaxRetries <= 0 {
		o.MaxRetries = 10
	}
	if o.RetryInterval <= 0 {
		o.RetryInterval = 2 * time.Second
	}
	if o.MaxConnections <= 0 {
		o.MaxConnections = 10
	}
}

func NewPostgresPool(ctx context.Context, dsn string, opts DBOptions, log *slog.Logger) (*pgxpool.Pool, error) {
	if log == nil {
		log = slog.Default()
	}
	opts.setDefaults()

	cfg, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("failed to parse postgres dsn: %w", err)
	}
	cfg.MaxConns = opts.MaxConnections

	var lastErr error
	for i := 1; i <= opts.MaxRetries; i++ {
		log.Info("connecting to postgres", "attempt", i, "max_retries", opts.MaxRetries)

		pool, err := pgxpool.NewWithConfig(ctx, cfg)
		if err != nil {
			lastErr = err
		} else {
			pingCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
			pingErr := pool.Ping(pingCtx)
			cancel()

			if pingErr == nil {
				log.Info("postgres connected")
				return pool, nil
			}

			lastErr = pingErr
			pool.Close()
		}

		if i < opts.MaxRetries {
			log.Warn("postgres not ready", "err", lastErr, "retry_in", opts.RetryInterval)
			select {
			case <-time.After(opts.RetryInterval):
			case <-ctx.Done():
				return nil, ctx.Err()
			}
		}
	}

	if lastErr == nil {
		lastErr = errors.New("unknown postgres connection error")
	}
	return nil, fmt.Errorf("could not connect to postgres after %d attempts: %w", opts.MaxRetries, lastErr)
}
