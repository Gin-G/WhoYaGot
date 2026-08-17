// Generational suffixes belong with the surname, not billed as one. The league
// is full of them — without this, "Marvin Harrison Jr." reads as a giant "JR."
const SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'])

// Particles are part of the surname that follows them. Splitting on the last
// word alone would file Amon-Ra St. Brown under "Brown" and Andrew Van Ginkel
// under "Ginkel" — wrong on the screen, and unmatchable on an import that
// wants "Last, First".
const PARTICLES = new Set(['st.', 'st', 'van', 'von', 'de', 'del', 'de la', 'la', 'le', 'da', 'di', 'der'])

/**
 * "Christian McCaffrey" -> given "Christian", family "McCaffrey".
 *
 * The surname is the last word, plus any suffix hanging off it and any
 * particle leading into it. Whatever is left in front is the given name, so a
 * player always keeps at least one word on each side.
 */
export function splitName(name: string): { given: string; family: string } {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 1) return { given: '', family: parts[0] ?? '' }

  let cut = parts.length - 1
  if (cut > 1 && SUFFIXES.has(parts[cut].toLowerCase())) cut -= 1
  while (cut > 1 && PARTICLES.has(parts[cut - 1].toLowerCase())) cut -= 1

  return { given: parts.slice(0, cut).join(' '), family: parts.slice(cut).join(' ') }
}

/**
 * "Marvin Harrison Jr." -> "Harrison Jr., Marvin".
 *
 * The other order fantasy sites accept on a pasted draft list. The suffix stays
 * on the surname, which is where those sites file it.
 */
export function lastFirst(name: string): string {
  const { given, family } = splitName(name)
  return given ? `${family}, ${given}` : family
}
