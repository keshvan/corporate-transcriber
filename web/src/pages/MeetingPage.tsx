import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getMeetingTranscript } from '../api/meetings'
import PageState from '../components/PageState'
import TranscriptView from '../components/TranscriptView'
import type { MeetingTranscript } from '../types'

export default function MeetingPage() {
  const { meetingId = '' } = useParams()
  const [transcript, setTranscript] = useState<MeetingTranscript | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    setTranscript(null)
    getMeetingTranscript(meetingId, controller.signal).then(setTranscript).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Не удалось загрузить транскрипцию.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [meetingId])

  return <div className="content">
    <Link className="back-link" to="/meetings">← Все встречи</Link>
    <div className="page-head meeting-page-head"><div><h1>Транскрипция</h1><p className="meeting-id">ID: {meetingId}</p></div></div>
    {loading ? <PageState title="Загрузка" message="Получаем транскрипцию встречи…" /> : error ? <PageState title={error.includes('not found') ? 'Транскрипция не найдена' : 'Не удалось загрузить транскрипцию'} message={error} action={<Link className="secondary-button" to="/meetings">Вернуться к встречам</Link>} /> : transcript ? <TranscriptView transcript={transcript} /> : null}
  </div>
}
