export type Meeting = {
  id: string
  created_at: string
}

export type MeetingSpeaker = {
  id: string
  meeting_id: string
  label: string
  speech_ms?: number
  embedding_status: string
  suggested_person_id?: string
  suggested_score?: number
}

export type TranscriptSegment = {
  id: string
  transcript_id: string
  segment_index: number
  text: string
  start_ms: number
  end_ms: number
  speaker?: MeetingSpeaker | null
}

export type MeetingTranscript = {
  id: string
  meeting_id: string
  full_text: string
  language?: string
  model: string
  created_at: string
  updated_at: string
  speakers: MeetingSpeaker[]
  segments: TranscriptSegment[]
}
