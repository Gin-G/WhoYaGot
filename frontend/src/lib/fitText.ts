import { useLayoutEffect, useRef } from 'react'

/**
 * Shrinks an element's font size until its text fits on one line.
 *
 * Names run from "Bo Nix" to "Chigoziem Okonkwo", and one fixed size either
 * wraps the long ones or wastes the width on the short ones. Measuring beats
 * guessing here: a character-count heuristic is wrong the moment a name is all
 * wide letters, and these are set in a condensed face where it is wrong often.
 */
export function useFitText<T extends HTMLElement>(text: string, minScale = 0.5) {
  const ref = useRef<T>(null)

  useLayoutEffect(() => {
    const el = ref.current
    const box = el?.parentElement
    if (!el || !box) return

    const fit = () => {
      // Back to the stylesheet's size first, so re-fitting is idempotent —
      // otherwise every pass would shrink again from the last result.
      el.style.fontSize = ''
      const available = el.clientWidth
      const needed = el.scrollWidth
      if (!available || needed <= available) return
      const base = parseFloat(getComputedStyle(el).fontSize)
      if (!base) return
      el.style.fontSize = `${base * Math.max(minScale, available / needed)}px`
    }

    fit()

    // The webfont lands after first paint and is narrower than the fallback,
    // so a fit measured before it arrives is measured against the wrong glyphs.
    void document.fonts?.ready.then(fit)

    // Rotation changes the width a name has to live in.
    const observer = new ResizeObserver(fit)
    observer.observe(box)
    return () => observer.disconnect()
  }, [text, minScale])

  return ref
}
