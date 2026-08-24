import { useCallback, useEffect, useRef, useState } from 'react'

import { describeError } from '../api/client'
import { useMatchup, useSkip, useUndoPick, useVote } from '../api/hooks'
import type { Matchup } from '../api/types'
import { MatchupStage } from '../components/MatchupStage'
import { PositionChips } from '../components/PositionChips'
import { Loading, StatusNote } from '../components/StatusNote'

/** How long the winner stays flooded before the next pair arrives. */
const HOLD_MS = 460

interface Props {
  league: string
  positions: string[]
  position: string | null
  onPositionChange: (position: string | null) => void
}

export function VotePage({ league, positions, position, onPositionChange }: Props) {
  const matchupQuery = useMatchup(league, position, Boolean(league))
  const vote = useVote(league, position)
  const skip = useSkip(league, position)
  const undo = useUndoPick()

  const [picked, setPicked] = useState<'a' | 'b' | null>(null)
  const [result, setResult] = useState<{
    rating: number
    delta: number
    agrees?: number
    differs?: number
  } | null>(null)
  const [votes, setVotes] = useState<number | null>(null)

  // The pick just made, kept only so it can be taken back. A pick made too
  // fast is the one you want back, and you want it back immediately.
  const [last, setLast] = useState<{ id: number; winner: string; loser: string } | null>(null)

  // The vote response swaps the next pair into the cache immediately, so the
  // displayed matchup is frozen during the flood — otherwise the half that just
  // won would change players mid-animation.
  const [displayed, setDisplayed] = useState<Matchup | null>(null)
  const timer = useRef<number | null>(null)

  useEffect(() => {
    if (!picked && matchupQuery.data) setDisplayed(matchupQuery.data)
  }, [matchupQuery.data, picked])

  useEffect(() => {
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [])

  // Switching position or league mid-flood should abandon it cleanly.
  useEffect(() => {
    setPicked(null)
    setResult(null)
  }, [league, position])

  const handlePick = useCallback(
    async (side: 'a' | 'b') => {
      if (!displayed || picked) return
      const winner = side === 'a' ? displayed.player_a : displayed.player_b
      const loser = side === 'a' ? displayed.player_b : displayed.player_a

      setPicked(side)
      const startedAt = Date.now()

      try {
        const outcome = await vote.mutateAsync({
          matchupId: displayed.id,
          winnerId: winner.id,
        })
        setResult({
          rating: outcome.ratings.global.winner.rating,
          delta: outcome.ratings.global.winner.delta,
          agrees: outcome.crowd_agrees,
          differs: outcome.crowd_differs,
        })
        setVotes(outcome.total_votes)
        setLast({ id: outcome.pick_id, winner: winner.name, loser: loser.name })
      } catch {
        // Leave the flood up briefly anyway; the error surfaces below the stage.
      }

      // Hold the payoff for a beat, but never longer than it takes to read.
      const elapsed = Date.now() - startedAt
      timer.current = window.setTimeout(
        () => {
          setPicked(null)
          setResult(null)
        },
        Math.max(0, HOLD_MS - elapsed),
      )
    },
    [displayed, picked, vote],
  )

  const handleSkip = useCallback(() => {
    if (!displayed || picked) return
    skip.mutate(displayed.id)
  }, [displayed, picked, skip])

  const handleUndo = useCallback(() => {
    if (!last || undo.isPending) return
    undo.mutate(last.id, {
      onSuccess: () => {
        setLast(null)
        setVotes((n) => (n === null ? n : n - 1))
      },
    })
    // The pair on screen is untouched — only the pick behind it is withdrawn.
  }, [last, undo])

  // Keyboard: left/right (or A/B) to pick, S to skip.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return
      const key = event.key.toLowerCase()
      if (key === 'arrowleft' || key === 'arrowup' || key === 'a') void handlePick('a')
      else if (key === 'arrowright' || key === 'arrowdown' || key === 'b') void handlePick('b')
      else if (key === 's') handleSkip()
      else if (key === 'u') handleUndo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [handlePick, handleSkip, handleUndo])

  const failure = matchupQuery.isError ? describeError(matchupQuery.error) : null

  return (
    <div className="flex h-full flex-col bg-concrete">
      <div className="shrink-0 border-b-2 border-ink">
        <PositionChips positions={positions} value={position} onChange={onPositionChange} />
      </div>

      <div className="relative min-h-0 flex-1">
        {failure ? (
          <StatusNote
            tone="alert"
            title="No matchup"
            detail={failure}
            action={
              <button
                type="button"
                onClick={() => void matchupQuery.refetch()}
                className="sign mt-2 border-2 border-ink px-4 py-2 text-[0.65rem] hover:bg-ink hover:text-chalk"
              >
                Try again
              </button>
            }
          />
        ) : displayed ? (
          <MatchupStage
            matchup={displayed}
            picked={picked}
            result={result}
            onPick={(side) => void handlePick(side)}
          />
        ) : (
          <Loading />
        )}
      </div>

      <div className="pb-inset flex shrink-0 items-center justify-between gap-3 border-t-2 border-ink px-4 py-2 md:pb-2">
        <span className="tabular min-w-0 truncate text-[0.65rem] uppercase tracking-wider text-ink-soft">
          {votes === null ? 'Tap a player' : `${votes} ${votes === 1 ? 'pick' : 'picks'}`}
        </span>
        <span className="sign hidden text-[0.6rem] text-ink-soft md:block">
          ← → to pick · S to skip{last ? ' · U to undo' : ''}
        </span>
        {last && (
          <button
            type="button"
            onClick={handleUndo}
            disabled={undo.isPending}
            title={`Take back ${last.winner} over ${last.loser}`}
            className="sign shrink-0 border-2 border-signal px-3 py-1.5 text-[0.62rem] text-ink transition-colors hover:bg-signal hover:text-chalk disabled:opacity-35"
          >
            Undo
          </button>
        )}
        <button
          type="button"
          onClick={handleSkip}
          disabled={!displayed || picked !== null || skip.isPending}
          className="sign border-2 border-ink px-3 py-1.5 text-[0.62rem] text-ink transition-colors hover:bg-ink hover:text-chalk disabled:opacity-35 disabled:hover:bg-transparent disabled:hover:text-ink"
        >
          Skip
        </button>
      </div>

      {/* Bottom nav clearance on phones. */}
      <div className="h-11 shrink-0 md:hidden" />
    </div>
  )
}
