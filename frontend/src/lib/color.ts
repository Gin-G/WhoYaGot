/**
 * Team colors come straight from the data, so the UI has to cope with whatever
 * turns up: near-black (Raiders), near-white, gold, and two teams that share a
 * navy. These helpers keep text legible and keep the two halves distinguishable.
 */

const FALLBACK = '#2A3038'

interface Rgb {
  r: number
  g: number
  b: number
}

function parseHex(hex?: string | null): Rgb | null {
  if (!hex) return null
  const clean = hex.trim().replace('#', '')
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean
  if (!/^[0-9a-fA-F]{6}$/.test(full)) return null
  return {
    r: parseInt(full.slice(0, 2), 16),
    g: parseInt(full.slice(2, 4), 16),
    b: parseInt(full.slice(4, 6), 16),
  }
}

function toHex({ r, g, b }: Rgb): string {
  const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)))
  return `#${[r, g, b].map((v) => clamp(v).toString(16).padStart(2, '0')).join('')}`
}

/** WCAG relative luminance. */
export function luminance(hex?: string | null): number {
  const rgb = parseHex(hex) ?? parseHex(FALLBACK)!
  const channel = (v: number) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(rgb.r) + 0.7152 * channel(rgb.g) + 0.0722 * channel(rgb.b)
}

/** Ink on light team colors, chalk on dark ones. */
export function readableOn(hex?: string | null): string {
  return luminance(hex) > 0.42 ? '#14171A' : '#F5F3EF'
}

export function mix(hex: string | null | undefined, target: string, amount: number): string {
  const a = parseHex(hex) ?? parseHex(FALLBACK)!
  const b = parseHex(target)!
  return toHex({
    r: a.r + (b.r - a.r) * amount,
    g: a.g + (b.g - a.g) * amount,
    b: a.b + (b.b - a.b) * amount,
  })
}

/** How far apart two colors look, 0–1. */
export function distance(a?: string | null, b?: string | null): number {
  const x = parseHex(a) ?? parseHex(FALLBACK)!
  const y = parseHex(b) ?? parseHex(FALLBACK)!
  const d = Math.sqrt((x.r - y.r) ** 2 + (x.g - y.g) ** 2 + (x.b - y.b) ** 2)
  return d / 441.67
}

export interface Field {
  /** CSS background for the half. */
  background: string
  /** Legible text color on top of it. */
  text: string
  /** Flat base color, for the flood animation. */
  base: string
}

/**
 * Paint one half of the stage.
 *
 * A pure flat fill goes muddy on very dark team colors, so each half gets a
 * shallow gradient lit from its own outer edge — which also reads as stadium
 * lighting falling across the field.
 */
export function fieldFor(color: string | null | undefined, side: 'a' | 'b'): Field {
  const base = parseHex(color) ? color!.trim() : FALLBACK
  const lum = luminance(base)

  // Dark colors get lifted, light colors get deepened — either way the
  // gradient stays visible rather than clipping to solid.
  const lift = lum < 0.2 ? 0.16 : lum > 0.6 ? -0.12 : 0.09
  const near = lift > 0 ? mix(base, '#FFFFFF', lift) : mix(base, '#14171A', -lift)
  const far = mix(base, '#14171A', 0.22)
  const angle = side === 'a' ? '145deg' : '325deg'

  return {
    background: `linear-gradient(${angle}, ${near} 0%, ${base} 45%, ${far} 100%)`,
    text: readableOn(base),
    base,
  }
}

/**
 * Two teams sharing a color would make the seam vanish. When that happens,
 * nudge the second half away so the split stays obvious.
 */
export function separate(colorA?: string | null, colorB?: string | null): string {
  if (distance(colorA, colorB) > 0.12) return colorB ?? FALLBACK
  const target = luminance(colorB) > 0.4 ? '#14171A' : '#FFFFFF'
  return mix(colorB, target, 0.28)
}
