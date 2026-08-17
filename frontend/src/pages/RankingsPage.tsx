import { useMemo } from 'react'

import { describeError } from '../api/client'
import { useRankings } from '../api/hooks'
import { LoadMore } from '../components/LoadMore'
import { PositionChips } from '../components/PositionChips'
import { RankingRow } from '../components/RankingRow'
import { Loading, StatusNote } from '../components/StatusNote'

interface Props {
  league: string
  positions: string[]
  position: string | null
  onPositionChange: (position: string | null) => void
}

export function RankingsPage({ league, positions, position, onPositionChange }: Props) {
  const query = useRankings(league, position, 'global')

  const pages = query.data?.pages
  const entries = useMemo(() => pages?.flatMap((page) => page.entries) ?? [], [pages])
  const total = pages?.[0]?.total ?? 0

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
            <h1 className="sign text-xs text-ink">Everyone's board</h1>
            <span className="tabular text-[0.65rem] uppercase tracking-wider text-ink-soft">
              {!pages ? '' : entries.length < total ? `${entries.length} of ${total}` : `${total} ranked`}
            </span>
          </div>

          {query.isLoading ? (
            <Loading label="Reading the board" />
          ) : query.isError ? (
            <StatusNote tone="alert" title="No rankings" detail={describeError(query.error)} />
          ) : entries.length > 0 ? (
            <>
              <ol>
                {entries.map((entry) => (
                  <RankingRow key={entry.player.id} entry={entry} />
                ))}
              </ol>
              {query.hasNextPage && (
                <LoadMore
                  onLoad={() => void query.fetchNextPage()}
                  loading={query.isFetchingNextPage}
                  remaining={total - entries.length}
                  noun="player"
                />
              )}
            </>
          ) : (
            <StatusNote
              title="Nothing ranked yet"
              detail="Players show up here once they've been in five matchups. Go make some picks."
            />
          )}
        </div>
      </div>
    </div>
  )
}
