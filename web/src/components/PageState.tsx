import type { ReactNode } from 'react'

type Props = { title: string; message: string; action?: ReactNode }

export default function PageState({ title, message, action }: Props) {
  return <div className="page-state" role="status"><div className="state-mark">{title === 'Загрузка' ? '…' : '!'}</div><h2>{title}</h2><p>{message}</p>{action}</div>
}
