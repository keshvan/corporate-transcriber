package kafka

type MeetingProcessingPayload struct {
	MeetingID      string  `json:"meeting_id"`
	AudioObjectKey string  `json:"audio_object_key"`
	Language       *string `json:"language,omitempty"`
}

type MeetingProcessingRequest struct {
	EventID       string                   `json:"event_id"`
	CorrelationID *string                  `json:"correlation_id,omitempty"`
	Payload       MeetingProcessingPayload `json:"payload"`
}
