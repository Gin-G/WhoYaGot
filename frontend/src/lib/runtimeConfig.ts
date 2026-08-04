/**
 * Configuration resolved at page load rather than at build time.
 *
 * The web container writes `config.js` on start-up, so one image can serve dev,
 * staging and production without a rebuild. Everywhere else — `npm run dev` and
 * the Android build, which has no server to generate the file — that script is
 * the empty stub in `public/`, and these fall back to Vite's compiled-in env.
 */

declare global {
  interface Window {
    __WHOYAGOT__?: {
      apiUrl?: string
      googleClientId?: string
    }
  }
}

/** Treats an unsubstituted or blank value as absent. */
function pick(...candidates: Array<string | undefined>): string | undefined {
  for (const value of candidates) {
    const trimmed = value?.trim()
    if (trimmed) return trimmed
  }
  return undefined
}

export const API_URL: string =
  pick(window.__WHOYAGOT__?.apiUrl, import.meta.env.VITE_API_URL) ?? '/api'

export const GOOGLE_CLIENT_ID: string =
  pick(window.__WHOYAGOT__?.googleClientId, import.meta.env.VITE_GOOGLE_CLIENT_ID) ?? ''
