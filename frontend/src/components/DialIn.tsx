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

/**
 * How wide the range opens at. A starting point, not a cap — the handles are
 * free of each other afterwards, and clamping them to a fixed width made
 * dragging one drag the other along, which is not what a pair of handles is
 * for.
 */
const OPENING_SPAN = 40

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
  const [to, setTo] = useState(value?.to ?? OPENING_SPAN)

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
    settle.current = window.setTimeout(
      () => onChange({ from: Math.min(from, to), to: Math.max(from, to) }),
      250,
    )
    return () => {
      if (settle.current) window.clearTimeout(settle.current)
    }
  }, [from, to, open, onChange])

  // Each handle answers only for itself. The range is whichever two places
  // they are on, read low to high, so one can be dragged past the other and
  // the range simply turns over rather than shoving the other handle down the
  // track ahead of it.
  const move = (edge: 'from' | 'to', raw: number) => {
    const next = clamp(raw, 1, top)
    if (edge === 'from') setFrom(next)
    else setTo(next)
  }

  const lo = Math.min(from, to)
  const hi = Math.max(from, to)

  const stop = () => {
    setOpen(false)
    onChange(null)
  }

  if (ranked < DIAL_MIN_BOARD) return null

  const left = ((lo - 1) / Math.max(top - 1, 1)) * 100
  const right = ((hi - 1) / Math.max(top - 1, 1)) * 100

  // The trigger lives in the action bar and the panel opens above it, so the
  // control is under the thumb that is already there rather than back up by
  // the position chips, where it had to share a crowded row on a phone.
  return (
    <>
      <button
        type="button"
        onClick={() =>
          open
            ? stop()
            : (setFrom(1), setTo(Math.min(OPENING_SPAN, top)), setOpen(true))
        }
        title="Work on one stretch of your board until it is right"
        className={[
          'sign shrink-0 border-2 px-3 py-1.5 text-[0.62rem] transition-colors',
          open
            ? 'border-signal bg-signal text-chalk'
            : 'border-ink/25 text-ink-soft hover:border-ink hover:text-ink',
        ].join(' ')}
      >
        {open ? `${lo}–${hi} ✕` : 'Dial it in'}
      </button>

      {open && (
        <div className="absolute inset-x-0 bottom-full z-10 border-t-2 border-ink bg-concrete px-4 py-3">
          {/* No close in here: the trigger below carries the range and shuts
              it, and two ways out of one panel is one too many. */}
          <span className="sign text-[0.58rem] text-ink">
            Dialling in {lo}–{hi} of {top}
          </span>

          <div className="relative mt-2 h-6">
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
            Dealing from {Math.max(1, lo - Math.max(5, Math.floor((hi - lo + 1) / 2)))}–
            {Math.min(top, hi + Math.max(5, Math.floor((hi - lo + 1) / 2)))}, because a
            stretch can only be settled against the players either side of it.
          </p>
        </div>
      )}
    </>
  )
}
