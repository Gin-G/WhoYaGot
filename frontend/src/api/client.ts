import axios from 'axios'

import { API_URL } from '../lib/runtimeConfig'
import { clearToken, getSessionId, getToken } from '../lib/session'

/**
 * Dev and the web container both go through a same-origin /api; the Android
 * build needs an absolute URL, since a webview has no proxy in front of it.
 */
export const API_BASE = API_URL

export const apiClient = axios.create({
  baseURL: API_BASE,
  timeout: 30000,
})

apiClient.interceptors.request.use((config) => {
  config.headers['X-Session-Id'] = getSessionId()
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // An expired session should drop us back to anonymous, not to a dead end.
    if (error.response?.status === 401 && getToken()) {
      clearToken()
    }
    return Promise.reject(error)
  },
)

/** Human-readable failure text for the UI. */
export function describeError(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (error.response) {
      const detail = error.response.data?.detail
      if (typeof detail === 'string') return detail
      return `Server returned ${error.response.status}.`
    }
    return "Can't reach the API. Check that the backend is running."
  }
  return 'Something went wrong.'
}
