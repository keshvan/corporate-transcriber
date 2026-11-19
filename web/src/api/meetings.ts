import type { Meeting, MeetingTranscript } from '../types'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, { signal })
  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`
    try {
      const body = await response.json() as { error?: string }
      if (body.error) message = body.error
    } catch {
      // Keep the HTTP status message when the response is not JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const getMeetings = (signal?: AbortSignal) => request<Meeting[]>('/meetings', signal)
export const getMeetingTranscript = (meetingId: string, signal?: AbortSignal) =>
  request<MeetingTranscript>(`/meetings/${encodeURIComponent(meetingId)}/transcript`, signal)
