import type { ReactNode } from 'react'

interface Props {
  title: string
  /** What to do next. Empty screens are an invitation to act, not a dead end. */
  detail?: ReactNode
  action?: ReactNode
  tone?: 'quiet' | 'alert'
}

export function StatusNote({ title, detail, action, tone = 'quiet' }: Props) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center">
      <div
        className={[
          'sign text-xs',
          tone === 'alert' ? 'text-signal' : 'text-ink-soft',
        ].join(' ')}
      >
        {title}
      </div>
      {detail && <p className="max-w-sm text-sm leading-relaxed text-ink-soft">{detail}</p>}
      {action}
    </div>
  )
}

export function Loading({ label = 'Dealing the next pair' }: { label?: string }) {
  return (
    <div className="flex h-full items-center justify-center">
      <span className="sign animate-pulse text-xs text-ink-soft">{label}</span>
    </div>
  )
}
