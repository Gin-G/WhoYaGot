import { useEffect, useState } from 'react'

import { describeError } from '../api/client'
import { useRankings } from '../api/hooks'
import { ExportPanel } from '../components/ExportPanel'
import { PositionChips } from '../components/PositionChips'
import { RankingRow } from '../components/RankingRow'
import { Loading, StatusNote } from '../components/StatusNote'
import { useAuth } from '../lib/auth'

interface Props {
  league: string
  positions: string[]
  position: string | null
  onPositionChange: (position: string | null) => void
}

export function MyListPage({ league, positions, position, onPositionChange }: Props) {
  const { user, enabled, signIn, error: authError } = useAuth()
  const query = useRankings(league, position, 'personal', Boolean(user))
  const [exporting, setExporting] = useState(false)

  // Only a settled response proves the board is empty. Treating "no data yet"
  // as empty would shut the panel every time a position chip is tapped, since
  // the new position has nothing cached to answer with.
  const boardEmpty = Boolean(query.data) && query.data!.entries.length === 0
  const canExport = Boolean(user) && !query.isError && !boardEmpty

  // A board with nothing on it has nothing to hand over.
  useEffect(() => {
    if (!canExport) setExporting(false)
  }, [canExport])

  return (
    <div className="flex h-full flex-col bg-concrete-light">
      <div className="shrink-0 border-b-2 border-ink bg-concrete">
        <PositionChips
          positions={positions}
          value={position}
          onChange={onPositionChange}
          allLabel="All"
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-3 pb-16 pt-4 md:pb-8">
          <div className="mb-3 flex items-baseline justify-between gap-3 border-b-2 border-ink pb-2">
            <h1 className="sign text-xs text-ink">Your board</h1>
            <div className="flex items-baseline gap-3">
              <span className="tabular text-[0.65rem] uppercase tracking-wider text-ink-soft">
                {query.data ? `${query.data.total} ranked` : ''}
              </span>
              {canExport && (
                <button
                  type="button"
                  aria-expanded={exporting}
                  onClick={() => setExporting((open) => !open)}
                  title="Take this list to another app"
                  className="sign shrink-0 border-2 border-ink px-2.5 py-1 text-[0.58rem] text-ink transition-colors hover:bg-ink hover:text-chalk"
                >
                  {exporting ? 'Close' : 'Export'}
                </button>
              )}
            </div>
          </div>

          {exporting && <ExportPanel league={league} position={position} />}

          {!user ? (
            <StatusNote
              title="Sign in to keep your list"
              detail={
                enabled
                  ? 'Your picks so far are saved on this device. Sign in and they carry over to your account.'
                  : 'Google sign-in is not configured yet. Set VITE_GOOGLE_CLIENT_ID in the frontend and GOOGLE_CLIENT_IDS on the API.'
              }
              action={
                enabled ? (
                  <button
                    type="button"
                    onClick={() => void signIn()}
                    className="sign mt-2 border-2 border-ink px-4 py-2 text-[0.65rem] hover:bg-ink hover:text-chalk"
                  >
                    Sign in with Google
                  </button>
                ) : undefined
              }
            />
          ) : query.isLoading ? (
            <Loading label="Reading your board" />
          ) : query.isError ? (
            <StatusNote tone="alert" title="No list" detail={describeError(query.error)} />
          ) : query.data && query.data.entries.length > 0 ? (
            <ol>
              {query.data.entries.map((entry) => (
                <RankingRow key={entry.player.id} entry={entry} showPicks />
              ))}
            </ol>
          ) : (
            <StatusNote
              title="No list yet"
              detail="Make a few picks and this builds itself — every matchup you answer moves a player up or down."
            />
          )}

          {authError && (
            <p className="sign mt-4 text-center text-[0.62rem] text-signal">{authError}</p>
          )}
        </div>
      </div>
    </div>
  )
}
