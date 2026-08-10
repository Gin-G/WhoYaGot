import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'

import type { League } from '../api/types'
import { useAuth } from '../lib/auth'

function Initial({ label }: { label: string }) {
  return (
    <span className="sign flex h-8 w-8 items-center justify-center rounded-full border-2 border-ink text-[0.62rem]">
      {label.slice(0, 1)}
    </span>
  )
}

/**
 * Google's avatar host is reachable from the Android webview, but the image
 * still does not always paint there. Falling back to the initial keeps a
 * signed-in account looking signed in instead of showing an empty ring.
 */
function Avatar({ src, label }: { src: string; label: string }) {
  const [failed, setFailed] = useState(false)

  // A new account means a new URL that deserves its own attempt.
  useEffect(() => setFailed(false), [src])

  if (failed) return <Initial label={label} />

  return (
    <img
      src={src}
      alt=""
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="h-8 w-8 rounded-full border-2 border-ink object-cover"
    />
  )
}

const NAV = [
  { to: '/', label: 'Pick', end: true },
  { to: '/rankings', label: 'Rankings', end: false },
  { to: '/my-list', label: 'My list', end: false },
  { to: '/picks', label: 'Picks', end: false },
]

function navClass({ isActive }: { isActive: boolean }): string {
  return [
    'sign relative px-3 py-2 text-[0.7rem] transition-colors md:text-xs',
    isActive ? 'text-ink' : 'text-ink-soft hover:text-ink',
    // The active marker is the only place the signal color appears.
    isActive
      ? 'after:absolute after:inset-x-2 after:-bottom-px after:h-[3px] after:bg-signal after:content-[""]'
      : '',
  ].join(' ')
}

interface Props {
  leagues: League[]
  league: string
  onLeagueChange: (key: string) => void
}

export function TopBar({ leagues, league, onLeagueChange }: Props) {
  const { user, enabled, signIn, signOut } = useAuth()

  return (
    <>
      <header className="pt-inset relative z-20 flex items-center justify-between gap-3 border-b-2 border-ink bg-concrete px-4 pb-2">
        <div className="flex min-w-0 items-center gap-4">
          {/* The brand is the seam: a slash between two calls. */}
          <NavLink to="/" className="flex shrink-0 items-baseline gap-1.5" aria-label="Who Ya Got">
            <span className="sign-tight text-sm font-extrabold text-ink md:text-base">Who</span>
            <span aria-hidden className="text-signal text-lg font-bold md:text-xl">
              /
            </span>
            <span className="sign-tight text-sm font-extrabold text-ink md:text-base">Ya Got</span>
          </NavLink>

          {leagues.length > 1 && (
            <div className="flex gap-1 overflow-x-auto">
              {leagues.map((l) => (
                <button
                  key={l.key}
                  type="button"
                  onClick={() => onLeagueChange(l.key)}
                  disabled={!l.available}
                  title={l.available ? undefined : `${l.name} has no players synced yet`}
                  className={[
                    'sign shrink-0 border-2 px-2.5 py-1 text-[0.62rem] transition-colors',
                    l.key === league
                      ? 'border-ink bg-ink text-chalk'
                      : 'border-ink/25 text-ink-soft hover:border-ink',
                    l.available ? '' : 'cursor-not-allowed opacity-35 hover:border-ink/25',
                  ].join(' ')}
                >
                  {l.name}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          <nav className="hidden md:flex md:items-center">
            {NAV.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>

          {user ? (
            <button
              type="button"
              onClick={signOut}
              title={`${user.name ?? user.email ?? 'Signed in'} — sign out`}
              className="flex items-center gap-2"
            >
              {user.picture ? (
                <Avatar src={user.picture} label={user.name ?? user.email ?? '?'} />
              ) : (
                <Initial label={user.name ?? user.email ?? '?'} />
              )}
            </button>
          ) : (
            enabled && (
              <button
                type="button"
                onClick={() => void signIn()}
                className="sign border-2 border-ink px-3 py-1.5 text-[0.62rem] text-ink transition-colors hover:bg-ink hover:text-chalk"
              >
                Sign in
              </button>
            )
          )}
        </div>
      </header>

      {/* On phones the nav lives under the thumb instead. */}
      <nav className="pb-inset fixed inset-x-0 bottom-0 z-20 flex justify-around border-t-2 border-ink bg-concrete pt-1 md:hidden">
        {NAV.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navClass}>
            {item.label}
          </NavLink>
        ))}
      </nav>
    </>
  )
}
