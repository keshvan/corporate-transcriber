package kafka

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/segmentio/kafka-go"
)

type Producer struct {
	writer *kafka.Writer
	topic  string
	logger *slog.Logger
}

func NewProducer(brokers []string, topic string, logger *slog.Logger) (*Producer, error) {
	if len(brokers) == 0 {
		return nil, errors.New("Kafka requires at least one broker")
	}
	for i := range brokers {
		brokers[i] = strings.TrimSpace(brokers[i])
		if brokers[i] == "" {
			return nil, errors.New("Kafka broker address must not be empty")
		}
	}
	if strings.TrimSpace(topic) == "" {
		return nil, errors.New("Kafka topic must not be empty")
	}
	if logger == nil {
		logger = slog.Default()
	}

	writer := &kafka.Writer{
		Addr:     kafka.TCP(brokers...),
		Topic:    topic,
		Balancer: &kafka.LeastBytes{},
	}

	return &Producer{
		writer: writer,
		topic:  topic,
		logger: logger,
	}, nil
}

// PublishMeetingProcessingRequest publishes a job for the Python meeting worker.
// The meeting ID is both the Kafka key and event ID, so retrying upload confirmation
// republishes the same idempotency key.
func (p *Producer) PublishMeetingProcessingRequest(
	ctx context.Context,
	meetingID, audioObjectKey string,
) error {
	if p == nil || p.writer == nil {
		return errors.New("Kafka producer is not initialized")
	}
	if strings.TrimSpace(meetingID) == "" || strings.TrimSpace(audioObjectKey) == "" {
		return errors.New("meeting ID and audio object key are required")
	}

	event := MeetingProcessingRequest{
		EventID: meetingID,
		Payload: MeetingProcessingPayload{
			MeetingID:      meetingID,
			AudioObjectKey: audioObjectKey,
		},
	}
	value, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("encode meeting processing event: %w", err)
	}

	if err := p.writer.WriteMessages(ctx, kafka.Message{
		Key:   []byte(meetingID),
		Value: value,
	}); err != nil {
		return fmt.Errorf("publish meeting processing event for %q to %q: %w", meetingID, p.topic, err)
	}

	p.logger.InfoContext(ctx, "meeting processing event published",
		"meeting_id", meetingID,
		"event_id", event.EventID,
		"topic", p.topic,
	)
	return nil
}

func (p *Producer) Close() error {
	if p == nil || p.writer == nil {
		return nil
	}
	if err := p.writer.Close(); err != nil {
		return fmt.Errorf("close Kafka producer: %w", err)
	}
	return nil
}
