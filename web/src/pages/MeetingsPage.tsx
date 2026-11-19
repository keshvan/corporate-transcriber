import { useEffect, useState } from 'react'
import MeetingList from '../components/MeetingList'
import PageState from '../components/PageState'
import { getMeetings } from '../api/meetings'
import type { Meeting } from '../types'

export default function MeetingsPage() {
  const [meetings, setMeetings] = useState<Meeting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getMeetings(controller.signal).then(setMeetings).catch(reason => {
      if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Не удалось загрузить встречи.')
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [reloadKey])

  return <div className="content">
    <div className="page-head"><div><h1>Встречи</h1><p>Записи встреч и их транскрипции</p></div></div>
    {loading ? <PageState title="Загрузка" message="Получаем список встреч проекта…" /> : error ? <PageState title="Не удалось загрузить встречи" message={error} action={<button className="secondary-button" onClick={() => setReloadKey(key => key + 1)}>Повторить</button>} /> : <><div className="list-summary">{meetings.length} {meetings.length === 1 ? 'встреча' : meetings.length >= 2 && meetings.length <= 4 ? 'встречи' : 'встреч'}</div><MeetingList meetings={meetings} /></>}
  </div>
}
