import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

import { describeError } from '../api/client'
import { usePicks, useRevisePick, useUndoPick } from '../api/hooks'
import type { Pick, PlayerCard } from '../api/types'
import { LoadMore } from '../components/LoadMore'
import { PositionChips } from '../components/PositionChips'
import { Loading, StatusNote } from '../components/StatusNote'

interface Props {
  league: string
  positions: string[]
  position: string | null
  onPositionChange: (position: string | null) => void
}

function when(iso: string): string {
  const then = new Date(iso)
  const mins = Math.round((Date.now() - then.getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  if (mins < 60 * 24) return `${Math.round(mins / 60)}h ago`
  return then.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

/**
 * One side of a pick. The winner reads as chosen and the loser as passed over,
 * so the row can be scanned without hunting for a label.
 */
function Side({
  player,
  won,
  onFilter,
  onChoose,
  busy,
}: {
  player: PlayerCard
  won: boolean
  onFilter: () => void
  onChoose: () => void
  busy: boolean
}) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2">
      <span
        aria-hidden
        className="h-8 w-1 shrink-0"
        style={{ background: player.team?.color ?? '#3A4046' }}
      />
      <div className="min-w-0 flex-1">
        <button
          type="button"
          onClick={onFilter}
          title={`Every pick ${player.name} was part of`}
          className={[
            'sign-tight block max-w-full truncate text-left text-[0.78rem] hover:underline md:text-sm',
            won ? 'text-ink' : 'text-ink-soft line-through decoration-ink/30',
          ].join(' ')}
        >
          {player.name}
        </button>
        <div className="tabular truncate text-[0.6rem] uppercase tracking-wider text-ink-soft">
          {[player.team?.abbr, player.position].filter(Boolean).join('  ·  ')}
        </div>
      </div>

      {/* The losing side is the button, because clicking it is the correction. */}
      {!won && (
        <button
          type="button"
          onClick={onChoose}
          disabled={busy}
          title={`Change this pick to ${player.name}`}
          className="sign shrink-0 border-2 border-ink/25 px-2 py-1 text-[0.58rem] text-ink-soft transition-colors hover:border-ink hover:bg-ink hover:text-chalk disabled:opacity-35"
        >
          Take him
        </button>
      )}
    </div>
  )
}

function PickRow({
  pick,
  onFilter,
  onRevise,
  onUndo,
  busy,
}: {
  pick: Pick
  onFilter: (player: PlayerCard) => void
  onRevise: (winnerId: number) => void
  onUndo: () => void
  busy: boolean
}) {
  return (
    <li className="border-b border-ink/12 py-2.5 pl-1 pr-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="tabular text-[0.58rem] uppercase tracking-wider text-ink-soft">
          {[pick.position, when(pick.created_at)].filter(Boolean).join('  ·  ')}
        </span>
        <button
          type="button"
          onClick={onUndo}
          disabled={busy}
          title="Take this pick back entirely"
          className="sign px-1 text-[0.58rem] uppercase tracking-wider text-ink-soft transition-colors hover:text-signal disabled:opacity-35"
        >
          Undo
        </button>
      </div>

      <div className="flex items-center gap-2">
        <Side
          player={pick.winner}
          won
          busy={busy}
          onFilter={() => onFilter(pick.winner)}
          onChoose={() => onRevise(pick.winner.id)}
        />
        <span aria-hidden className="sign shrink-0 text-[0.6rem] text-ink-soft">
          over
        </span>
        <Side
          player={pick.loser}
          won={false}
          busy={busy}
          onFilter={() => onFilter(pick.loser)}
          onChoose={() => onRevise(pick.loser.id)}
        />
      </div>
    </li>
  )
}

export function HistoryPage({ league, positions, position, onPositionChange }: Props) {
  const [params, setParams] = useSearchParams()
  const playerParam = params.get('player')
  const playerId = playerParam ? Number(playerParam) : null

  const query = usePicks(league, position, playerId)
  const undo = useUndoPick()
  const revise = useRevisePick()
  const busy = undo.isPending || revise.isPending

  const pages = query.data?.pages
  const picks = useMemo(() => pages?.flatMap((page) => page.picks) ?? [], [pages])
  const total = pages?.[0]?.total ?? 0
  // The filter names itself from the picks it returned, so no extra lookup.
  const filtered =
    playerId !== null
      ? (picks[0]?.winner.id === playerId ? picks[0]?.winner : picks[0]?.loser)
      : undefined

  const setPlayer = (id: number | null) => {
    setParams(id === null ? {} : { player: String(id) }, { replace: true })
  }

  const failure = query.isError ? describeError(query.error) : null
  const changeFailure = undo.error ?? revise.error

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
            <h1 className="sign text-xs text-ink">Your picks</h1>
            <span className="tabular text-[0.65rem] uppercase tracking-wider text-ink-soft">
              {!pages ? '' : picks.length < total ? `${picks.length} of ${total}` : `${total} made`}
            </span>
          </div>

          {playerId !== null && (
            <button
              type="button"
              onClick={() => setPlayer(null)}
              className="sign mb-3 flex w-full items-center justify-between border-2 border-ink px-3 py-2 text-[0.62rem] text-ink transition-colors hover:bg-ink hover:text-chalk"
            >
              <span className="truncate">
                Only {filtered?.name ?? 'this player'}
              </span>
              <span aria-hidden className="ml-2 shrink-0">
                clear ✕
              </span>
            </button>
          )}

          {changeFailure && (
            <p className="sign mb-3 text-[0.62rem] text-signal">
              {describeError(changeFailure)}
            </p>
          )}

          {failure ? (
            <StatusNote tone="alert" title="No picks" detail={failure} />
          ) : query.isLoading ? (
            <Loading label="Reading your picks" />
          ) : picks.length > 0 ? (
            <>
              <ol>
                {picks.map((pick) => (
                  <PickRow
                    key={pick.id}
                    pick={pick}
                    busy={busy}
                    onFilter={(player) => setPlayer(player.id)}
                    onRevise={(winnerId) => revise.mutate({ pickId: pick.id, winnerId })}
                    onUndo={() => undo.mutate(pick.id)}
                  />
                ))}
              </ol>
              {query.hasNextPage && (
                <LoadMore
                  onLoad={() => void query.fetchNextPage()}
                  loading={query.isFetchingNextPage}
                  remaining={total - picks.length}
                  noun="pick"
                />
              )}
            </>
          ) : (
            <StatusNote
              title={playerId !== null ? 'No picks with him' : 'Nothing picked yet'}
              detail={
                playerId !== null
                  ? 'You have not been dealt this player at this position yet.'
                  : 'Every pair you answer shows up here, and can be taken back or changed.'
              }
            />
          )}
        </div>
      </div>
    </div>
  )
}
