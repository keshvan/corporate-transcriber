import { useState, type FormEvent } from 'react'
import { uploadDocument, uploadMeeting } from '../api/meetings'

type UploadKind = 'meeting' | 'document'

type Props = {
  onClose: () => void
  onComplete: (kind: UploadKind, title: string) => void
}

function titleFromFilename(filename: string) {
  return filename.replace(/\.[^.]+$/, '')
}

export default function UploadDialog({ onClose, onComplete }: Props) {
  const [kind, setKind] = useState<UploadKind>('meeting')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [meetingAt, setMeetingAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  function chooseFile(nextFile: File | undefined) {
    setFile(nextFile ?? null)
    if (nextFile && !title.trim()) setTitle(titleFromFilename(nextFile.name))
    setError('')
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || !title.trim()) return
    setBusy(true)
    setError('')
    try {
      if (kind === 'meeting') {
        await uploadMeeting(file, title.trim(), meetingAt ? new Date(meetingAt).toISOString() : undefined)
      } else {
        await uploadDocument(file, title.trim())
      }
      onComplete(kind, title.trim())
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Не удалось загрузить файл.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="dialog-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="upload-dialog" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <div className="upload-dialog-head">
        <div><span className="eyebrow">НОВЫЙ МАТЕРИАЛ</span><h2 id="upload-title">Загрузить в проект</h2></div>
        <button className="dialog-close" type="button" aria-label="Закрыть" onClick={onClose} disabled={busy}>×</button>
      </div>

      <div className="upload-tabs" role="tablist" aria-label="Тип материала">
        <button type="button" role="tab" aria-selected={kind === 'meeting'} className={kind === 'meeting' ? 'selected' : ''} onClick={() => { setKind('meeting'); setError('') }}>Встреча</button>
        <button type="button" role="tab" aria-selected={kind === 'document'} className={kind === 'document' ? 'selected' : ''} onClick={() => { setKind('document'); setError('') }}>Документ</button>
      </div>

      <form onSubmit={submit}>
        <label className="upload-field">Файл
          <input type="file" required disabled={busy} onChange={event => chooseFile(event.target.files?.[0])} />
          <small>{file ? file.name : 'Выберите файл с устройства'}</small>
        </label>
        <label className="upload-field">Название
          <input type="text" required maxLength={200} value={title} onChange={event => setTitle(event.target.value)} placeholder={kind === 'meeting' ? 'Например, Планирование спринта' : 'Название документа'} disabled={busy} />
        </label>
        {kind === 'meeting' && <label className="upload-field">Дата встречи <span className="optional-label">необязательно</span>
          <input type="datetime-local" value={meetingAt} onChange={event => setMeetingAt(event.target.value)} disabled={busy} />
        </label>}

        {error && <p className="upload-error" role="alert">{error}</p>}
        <div className="upload-actions">
          <button className="secondary-button" type="button" onClick={onClose} disabled={busy}>Отмена</button>
          <button className="primary" type="submit" disabled={busy || !file || !title.trim()}>{busy ? 'Загрузка…' : 'Загрузить'}</button>
        </div>
      </form>
      <p className="upload-hint">Файл будет отправлен в хранилище, после чего проект подтвердит загрузку.</p>
    </section>
  </div>
}
