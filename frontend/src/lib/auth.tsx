import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { apiClient } from '../api/client'
import type { AuthResult, User } from '../api/types'
import { GOOGLE_CLIENT_ID } from './runtimeConfig'
import { clearToken, getSessionId, getToken, setToken } from './session'

const GSI_SRC = 'https://accounts.google.com/gsi/client'

interface AuthState {
  user: User | null
  loading: boolean
  /** False when no Google client ID is configured — voting still works. */
  enabled: boolean
  error: string | null
  signIn: () => Promise<void>
  signOut: () => void
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: Record<string, unknown>) => void
          prompt: (listener?: (notification: unknown) => void) => void
        }
      }
    }
  }
}

let gsiPromise: Promise<void> | null = null

function loadGsi(): Promise<void> {
  if (window.google?.accounts?.id) return Promise.resolve()
  if (gsiPromise) return gsiPromise

  gsiPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = GSI_SRC
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Could not load Google Sign-In.'))
    document.head.appendChild(script)
  })
  return gsiPromise
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      const { data } = await apiClient.get<User>('/auth/me')
      setUser(data)
    } catch {
      clearToken()
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const exchange = useCallback(async (credential: string) => {
    const { data } = await apiClient.post<AuthResult>('/auth/google', {
      credential,
      session_id: getSessionId(),
    })
    setToken(data.access_token)
    setUser(data.user)
    setError(null)
  }, [])

  const signIn = useCallback(async () => {
    if (!GOOGLE_CLIENT_ID) {
      setError('Google sign-in is not configured. Set VITE_GOOGLE_CLIENT_ID.')
      return
    }
    setError(null)
    try {
      await loadGsi()
      window.google!.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (response: { credential?: string }) => {
          if (response.credential) {
            void exchange(response.credential).catch(() =>
              setError('Google accepted the sign-in but the server rejected it.'),
            )
          }
        },
      })
      window.google!.accounts.id.prompt()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    }
  }, [exchange])

  const signOut = useCallback(() => {
    clearToken()
    setUser(null)
  }, [])

  const value = useMemo<AuthState>(
    () => ({ user, loading, enabled: Boolean(GOOGLE_CLIENT_ID), error, signIn, signOut, refresh }),
    [user, loading, error, signIn, signOut, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
