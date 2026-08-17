import { useEffect, useRef } from 'react'

interface Props {
  /** Asks for the next page. Safe to call while one is already in flight. */
  onLoad: () => void
  loading: boolean
  /** How many rows the list is still holding back. */
  remaining: number
  /** "player" / "pick" — pluralised here. */
  noun: string
}

/**
 * The foot of a long list: fetches the next page as it comes into reach, and
 * stays a real button for anyone who never gets there by scrolling.
 *
 * Auto-loading alone would strand keyboard and screen-reader users at a
 * boundary they cannot cross, and a button alone would make a board of a few
 * hundred a chore. Doing both costs one element.
 */
export function LoadMore({ onLoad, loading, remaining, noun }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  // Held in a ref so a fresh closure each render doesn't tear down the
  // observer and re-fire the moment it reattaches.
  const latest = useRef(onLoad)

  useEffect(() => {
    latest.current = onLoad
  })

  useEffect(() => {
    const node = ref.current
    if (!node) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) latest.current()
      },
      // Start the next page before the last row lands, so a steady scroll
      // never actually stops.
      { rootMargin: '400px' },
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={ref} className="flex justify-center py-4">
      {loading ? (
        <span className="sign animate-pulse text-[0.62rem] text-ink-soft">Loading</span>
      ) : (
        <button
          type="button"
          onClick={onLoad}
          className="sign border-2 border-ink px-4 py-2 text-[0.62rem] text-ink transition-colors hover:bg-ink hover:text-chalk"
        >
          Show {remaining} more {remaining === 1 ? noun : `${noun}s`}
        </button>
      )}
    </div>
  )
}
