import type { Meeting, MeetingTranscript } from '../types'
import { ACTIVE_PROJECT_ID } from './project'

const apiBase = import.meta.env.VITE_API_BASE_URL ?? '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init)
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

export const getMeetings = (signal?: AbortSignal) => request<Meeting[]>('/meetings', { signal })
export const getMeetingTranscript = (meetingId: string, signal?: AbortSignal) =>
  request<MeetingTranscript>(`/meetings/${encodeURIComponent(meetingId)}/transcript`, { signal })

type PresignedUpload = {
  url: string
  method: string
  headers: Record<string, string>
  expires_in_seconds: number
}

type UploadInitialization<T> = { upload: PresignedUpload; meeting?: T; document?: T }

export type UploadedMaterial = { id: string; title: string }

async function uploadFile<T>(
  kind: 'meetings' | 'documents',
  file: File,
  title: string,
  meetingAt?: string,
): Promise<UploadedMaterial> {
  const contentType = file.type || 'application/octet-stream'
  const initPath = `/projects/${ACTIVE_PROJECT_ID}/${kind}/uploads`
  const body = kind === 'meetings'
    ? { title, filename: file.name, content_type: contentType, ...(meetingAt ? { meeting_at: meetingAt } : {}) }
    : { title, filename: file.name, content_type: contentType }
  const initialized = await request<UploadInitialization<UploadedMaterial>>(initPath, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  const { upload } = initialized
  const putResponse = await fetch(upload.url, {
    method: upload.method || 'PUT',
    headers: upload.headers,
    body: file,
  })
  if (!putResponse.ok) {
    throw new Error(`Не удалось отправить файл в хранилище (${putResponse.status}).`)
  }

  const material = initialized.meeting ?? initialized.document
  if (!material) throw new Error('Сервер не вернул данные загруженного файла.')
  return request<UploadedMaterial>(
    `/projects/${ACTIVE_PROJECT_ID}/${kind}/${encodeURIComponent(material.id)}/uploads/complete`,
    { method: 'POST' },
  )
}

export const uploadMeeting = (file: File, title: string, meetingAt?: string) =>
  uploadFile('meetings', file, title, meetingAt)

export const uploadDocument = (file: File, title: string) => uploadFile('documents', file, title)
