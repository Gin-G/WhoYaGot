/**
 * Local identity.
 *
 * A session ID lets someone vote before signing in; the backend claims those
 * votes onto their account the first time they authenticate with it. The token
 * is the WhoYaGot session JWT, not the Google one.
 */

const SESSION_KEY = 'whoyagot.session_id'
const TOKEN_KEY = 'whoyagot.token'

function randomId(): string {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function getSessionId(): string {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = randomId()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}
