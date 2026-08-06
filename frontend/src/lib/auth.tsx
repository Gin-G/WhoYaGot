import { GoogleAuth } from '@codetrix-studio/capacitor-google-auth'
import { Capacitor } from '@capacitor/core'
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

import { apiClient } from '../api/client'
import type { AuthResult, User } from '../api/types'
import { GOOGLE_CLIENT_ID } from './runtimeConfig'
import { clearToken, getSessionId, getToken, setToken } from './session'

const GSI_SRC = 'https://accounts.google.com/gsi/client'

// Google refuses its web sign-in flow inside a webview, so the Android build
// cannot use GSI at all — it goes through Play Services natively instead. Both
// paths end at the same place: an ID token posted to POST /auth/google.
const IS_NATIVE = Capacitor.isNativePlatform()

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

/** Play Services status code, which the plugin rejects with as the error code. */
function statusCode(err: unknown): string {
  if (typeof err === 'object' && err !== null && 'code' in err) {
    return String((err as { code: unknown }).code ?? '')
  }
  return ''
}

/** Play Services reports a dismissed account picker as error 12501. */
function isCancellation(err: unknown): boolean {
  const message = err instanceof Error ? err.message : String(err ?? '')
  return statusCode(err) === '12501' || message.includes('12501') || /cancel/i.test(message)
}

/**
 * The plugin collapses every Play Services failure into "Something went wrong"
 * and puts the only useful detail — the status code — somewhere the message
 * never shows. Pull it back out, and translate the one that actually happens.
 */
function describeSignInError(err: unknown): string {
  const code = statusCode(err)
  if (code === '10') {
    return (
      'Google rejected this build (code 10). Its package name and signing ' +
      'certificate are not registered as an Android OAuth client.'
    )
  }
  const message = err instanceof Error ? err.message : 'Sign-in failed.'
  return code ? `${message} (code ${code})` : message
}

let nativePromise: Promise<void> | null = null

/** Idempotent: initialize() builds the Play Services client, so it runs once. */
function initNative(): Promise<void> {
  if (!nativePromise) {
    nativePromise = GoogleAuth.initialize({
      clientId: GOOGLE_CLIENT_ID,
      scopes: ['profile', 'email'],
      grantOfflineAccess: false,
    })
  }
  return nativePromise
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
      if (IS_NATIVE) {
        await initNative()
        const account = await GoogleAuth.signIn()
        const idToken = account.authentication?.idToken
        if (!idToken) throw new Error('Google signed you in but returned no ID token.')
        try {
          await exchange(idToken)
        } catch {
          setError('Google accepted the sign-in but the server rejected it.')
        }
        return
      }

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
      // Backing out of the native account picker is a choice, not a failure.
      if (isCancellation(err)) return
      setError(describeSignInError(err))
    }
  }, [exchange])

  const signOut = useCallback(() => {
    // Without this Play Services hands back the same account next time and
    // signing out looks broken to anyone trying to switch.
    if (IS_NATIVE) void GoogleAuth.signOut().catch(() => undefined)
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
