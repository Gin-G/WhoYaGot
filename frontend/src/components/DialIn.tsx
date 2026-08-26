import { useEffect, useRef, useState } from 'react'

import type { Dial } from '../api/hooks'

interface Props {
  /** How many players the voter has ranked; the dial cannot reach past it. */
  ranked: number
  value: Dial | null
  onChange: (dial: Dial | null) => void
}

/** Below this there is no order worth dialling into — go and vote first. */
export const DIAL_MIN_BOARD = 12

/** Widest stretch worth working on at once. */
const MAX_SPAN = 40

function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value))
}

/**
 * Pick the stretch of your board to settle.
 *
 * Two handles over one track, because the thing being chosen is a range and a
 * pair of number boxes makes you read to know what you have. The track is the
 * board, the filled part is the stretch — the same shape as the list it stands
 * for, so the control says where you are working without a label being read.
 *
 * The draw reaches past both ends of what is chosen, which is the whole point
 * and so is written under it: a range cannot be settled against itself.
 */
export function DialIn({ ranked, value, onChange }: Props) {
  const top = Math.max(ranked, 1)
  const [open, setOpen] = useState(value !== null)
  const [from, setFrom] = useState(value?.from ?? 1)
  const [to, setTo] = useState(value?.to ?? MAX_SPAN)

  // The board's depth arrives after this mounts — the count comes from a query.
  // A default worked out at mount would be worked out against a board of
  // nothing, which is how this opened at 1-1 with handles that would not move.
  // So the range is fitted to the board whenever the board changes, and again
  // on the way open.
  useEffect(() => {
    setTo((current) => clamp(current, 1, top))
    setFrom((current) => clamp(current, 1, top))
  }, [top])

  // The handles are dragged continuously; the board should not be re-dealt on
  // every pixel of that. Settle first, then ask.
  const settle = useRef<number | null>(null)
  useEffect(() => {
    if (!open) return
    if (settle.current) window.clearTimeout(settle.current)
    settle.current = window.setTimeout(() => onChange({ from, to }), 250)
    return () => {
      if (settle.current) window.clearTimeout(settle.current)
    }
  }, [from, to, open, onChange])

  const move = (edge: 'from' | 'to', raw: number) => {
    const next = clamp(raw, 1, top)
    if (edge === 'from') {
      setFrom(next)
      // The handles pass through each other rather than jamming, which is what
      // a hand expects when it drags one past the other.
      if (next > to) setTo(next)
      if (to - next > MAX_SPAN) setTo(next + MAX_SPAN)
    } else {
      setTo(next)
      if (next < from) setFrom(next)
      if (next - from > MAX_SPAN) setFrom(next - MAX_SPAN)
    }
  }

  const stop = () => {
    setOpen(false)
    onChange(null)
  }

  if (ranked < DIAL_MIN_BOARD) return null

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setFrom(1)
          setTo(Math.min(MAX_SPAN, top))
          setOpen(true)
        }}
        title="Work on one stretch of your board until it is right"
        className="sign shrink-0 border-2 border-ink/25 px-3 py-1 text-[0.58rem] text-ink-soft transition-colors hover:border-ink hover:text-ink"
      >
        Dial it in
      </button>
    )
  }

  const left = ((from - 1) / Math.max(top - 1, 1)) * 100
  const right = ((to - 1) / Math.max(top - 1, 1)) * 100

  return (
    <div className="absolute inset-x-0 top-0 z-10 border-b-2 border-ink bg-concrete px-3 py-2 md:static md:w-[26rem] md:border-b-0 md:border-l-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="sign text-[0.58rem] text-ink">
          Dialling in {from}–{to}
        </span>
        <button
          type="button"
          onClick={stop}
          className="sign text-[0.58rem] uppercase tracking-wider text-ink-soft transition-colors hover:text-signal"
        >
          Done ✕
        </button>
      </div>

      <div className="relative mt-3 h-6">
        {/* The whole board, and the stretch being worked on. */}
        <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 bg-ink/20" />
        <div
          className="absolute top-1/2 h-1 -translate-y-1/2 bg-signal"
          style={{ left: `${left}%`, right: `${100 - right}%` }}
        />
        {(['from', 'to'] as const).map((edge) => (
          <input
            key={edge}
            type="range"
            min={1}
            max={top}
            value={edge === 'from' ? from : to}
            onChange={(event) => move(edge, Number(event.target.value))}
            aria-label={edge === 'from' ? 'First rank to settle' : 'Last rank to settle'}
            // Stacked transparent tracks: the visible bar is drawn above, and
            // pointer-events are handed back to the thumbs alone so whichever
            // is nearer the tap takes it.
            className="dial-handle absolute inset-x-0 top-0 h-6 w-full appearance-none bg-transparent"
          />
        ))}
      </div>

      <p className="mt-1 text-[0.62rem] leading-relaxed text-ink-soft">
        Dealing from {Math.max(1, from - Math.max(5, Math.floor((to - from + 1) / 2)))}–
        {Math.min(top, to + Math.max(5, Math.floor((to - from + 1) / 2)))}, because a
        stretch can only be settled against the players either side of it.
      </p>
    </div>
  )
}
