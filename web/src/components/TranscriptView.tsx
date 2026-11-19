import type { MeetingTranscript, TranscriptSegment } from '../types'

export function formatTime(milliseconds: number) {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000))
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  const hours = Math.floor(totalSeconds / 3600)
  return hours ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`
}

function Segment({ segment }: { segment: TranscriptSegment }) {
  return <article className="transcript-segment">
    <time className="segment-time">{formatTime(segment.start_ms)}</time>
    <div className="segment-content">
      <span className="speaker-label">{segment.speaker?.label ?? 'Говорящий не определён'}</span>
      <p>{segment.text || 'Нет текста для этого фрагмента.'}</p>
    </div>
  </article>
}

export default function TranscriptView({ transcript }: { transcript: MeetingTranscript }) {
  const suggestions = transcript.speakers.filter(speaker => speaker.suggested_person_id)
  return <div className="transcript-layout">
    <section className="transcript-card">
      <div className="transcript-title">
        <div className="file-icon meeting">◖</div>
        <div className="transcript-heading"><b>Транскрипция встречи</b><small>{transcript.segments.length} фрагм. · модель {transcript.model}{transcript.language ? ` · ${transcript.language}` : ''}</small></div>
      </div>
      {transcript.segments.length ? <div className="segments">{transcript.segments.map(segment => <Segment key={segment.id} segment={segment} />)}</div> : <div className="empty">В транскрипции пока нет фрагментов.</div>}
    </section>
    <aside className="review-card">
      <div className="review-head"><div><h3>Говорящие</h3><p>Имена из распознавания речи</p></div><span className="review-number">{transcript.speakers.length}</span></div>
      {transcript.speakers.length ? transcript.speakers.map(speaker => <div className="speaker-card" key={speaker.id}>
        <span className="speaker-avatar">{speaker.label.slice(0, 1).toUpperCase()}</span>
        <div><b>{speaker.label}</b><small>{speaker.speech_ms == null ? 'Длительность не указана' : `Речь · ${formatTime(speaker.speech_ms)}`}</small>
          {speaker.suggested_person_id && <small className="suggestion">Есть автоматическое совпадение · {Math.round((speaker.suggested_score ?? 0) * 100)}%</small>}
        </div>
      </div>) : <p className="review-empty">Для этой встречи говорящие не указаны.</p>}
      {suggestions.length > 0 && <p className="review-note">Совпадения показаны как подсказки и требуют подтверждения.</p>}
    </aside>
  </div>
}
