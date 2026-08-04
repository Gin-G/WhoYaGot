import { describeError } from '../api/client'
import { useRankings } from '../api/hooks'
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
          <div className="mb-3 flex items-baseline justify-between border-b-2 border-ink pb-2">
            <h1 className="sign text-xs text-ink">Your board</h1>
            <span className="tabular text-[0.65rem] uppercase tracking-wider text-ink-soft">
              {query.data ? `${query.data.total} ranked` : ''}
            </span>
          </div>

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
                <RankingRow key={entry.player.id} entry={entry} />
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
