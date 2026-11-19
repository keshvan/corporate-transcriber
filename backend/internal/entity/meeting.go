package entity

import "time"

type Meeting struct {
	ID        string     `json:"id"`
	ProjectID string     `json:"project_id"`
	Title     string     `json:"title"`
	MeetingAt *time.Time `json:"meeting_at,omitempty"`
	CreatedAt time.Time  `json:"created_at"`
}

type MeetingTranscript struct {
	ID        string              `json:"id"`
	MeetingID string              `json:"meeting_id"`
	FullText  string              `json:"full_text"`
	Language  *string             `json:"language,omitempty"`
	Model     string              `json:"model"`
	CreatedAt time.Time           `json:"created_at"`
	UpdatedAt time.Time           `json:"updated_at"`
	Speakers  []MeetingSpeaker    `json:"speakers"`
	Segments  []TranscriptSegment `json:"segments"`
}

type MeetingSpeaker struct {
	ID              string    `json:"id"`
	MeetingID       string    `json:"meeting_id"`
	Label           string    `json:"label"`
	ParticipantID   *string   `json:"participant_id,omitempty"`
	ParticipantName *string   `json:"participant_name,omitempty"`
	SpeechMS        *int32    `json:"speech_ms,omitempty"`
	QdrantPointID   *string   `json:"qdrant_point_id,omitempty"`
	EmbeddingStatus string    `json:"embedding_status"`
	CreatedAt       time.Time `json:"created_at"`
	UpdatedAt       time.Time `json:"updated_at"`
}

type TranscriptSegment struct {
	ID           string          `json:"id"`
	TranscriptID string          `json:"transcript_id"`
	SegmentIndex int32           `json:"segment_index"`
	Text         string          `json:"text"`
	StartMS      int32           `json:"start_ms"`
	EndMS        int32           `json:"end_ms"`
	Speaker      *MeetingSpeaker `json:"speaker,omitempty"`
}
