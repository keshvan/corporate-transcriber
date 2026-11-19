import { Link } from 'react-router-dom'
import type { Meeting } from '../types'

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long', timeStyle: 'short' }).format(date)
}

export default function MeetingList({ meetings }: { meetings: Meeting[] }) {
  if (!meetings.length) return <div className="empty-state"><div className="empty-icon">◖</div><h2>Встреч пока нет</h2><p>Когда встречи появятся в проекте, они будут собраны здесь.</p></div>

  return <section className="meeting-list" aria-label="Список встреч">
    <div className="meeting-list-head"><span>ВСТРЕЧА</span><span>ДАТА ДОБАВЛЕНИЯ</span><span/></div>
    {meetings.map((meeting, index) => <Link className="meeting-row" key={meeting.id} to={`/meetings/${meeting.id}`}>
      <span className="meeting-identity"><span className="file-icon meeting">◖</span><span><b>Встреча {meetings.length - index}</b><small>{meeting.id}</small></span></span>
      <time dateTime={meeting.created_at}>{formatDate(meeting.created_at)}</time>
      <span className="row-arrow" aria-hidden="true">→</span>
    </Link>)}
  </section>
}
