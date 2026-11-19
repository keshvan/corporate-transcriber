package transport

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"time"
)

type HTTPServer struct {
	server *http.Server
	log    *slog.Logger
}

func NewHTTPServer(host string, port int, router http.Handler, log *slog.Logger) *HTTPServer {
	if log == nil {
		log = slog.Default()
	}

	return &HTTPServer{
		server: &http.Server{
			Addr:              net.JoinHostPort(host, fmt.Sprintf("%d", port)),
			Handler:           router,
			ReadHeaderTimeout: 5 * time.Second,
			IdleTimeout:       60 * time.Second,
		},
		log: log,
	}
}

func (s *HTTPServer) Run(ctx context.Context) error {
	errCh := make(chan error, 1)
	go func() {
		errCh <- s.server.ListenAndServe()
	}()

	s.log.Info("HTTP server started", "addr", s.server.Addr)
	select {
	case err := <-errCh:
		if errors.Is(err, http.ErrServerClosed) {
			return nil
		}
		return fmt.Errorf("serve HTTP: %w", err)
	case <-ctx.Done():
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		if err := s.server.Shutdown(shutdownCtx); err != nil {
			return fmt.Errorf("shutdown HTTP server: %w", err)
		}
		err := <-errCh
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			return fmt.Errorf("serve HTTP: %w", err)
		}
		s.log.Info("HTTP server stopped")
		return nil
	}
}
