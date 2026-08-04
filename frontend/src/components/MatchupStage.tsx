import type { Matchup } from '../api/types'
import { separate } from '../lib/color'
import { PlayerHalf } from './PlayerHalf'

interface Props {
  matchup: Matchup
  picked: 'a' | 'b' | null
  result: { rating: number; delta: number } | null
  onPick: (side: 'a' | 'b') => void
}

export function MatchupStage({ matchup, picked, result, onPick }: Props) {
  const { player_a: a, player_b: b } = matchup

  // Two teams in the same navy would make the seam vanish; nudge B's field.
  const colorB = separate(a.team?.color, b.team?.color)

  const stateFor = (side: 'a' | 'b') =>
    picked === null ? 'idle' : picked === side ? 'won' : 'lost'

  return (
    <div className="relative h-full w-full select-none overflow-hidden bg-ink">
      <PlayerHalf
        player={a}
        side="a"
        state={stateFor('a')}
        result={picked === 'a' ? result : null}
        onPick={() => onPick('a')}
        disabled={picked !== null}
      />
      <PlayerHalf
        player={b}
        side="b"
        colorOverride={colorB}
        state={stateFor('b')}
        result={picked === 'b' ? result : null}
        onPick={() => onPick('b')}
        disabled={picked !== null}
      />

      <div
        className={['stage-seam stage-seam-outer', picked ? 'stage-seam-hidden' : ''].join(' ')}
      />
      <div
        className={['stage-seam stage-seam-inner', picked ? 'stage-seam-hidden' : ''].join(' ')}
      />

      {/* The word that names the whole app, sitting on the fault line. */}
      <div
        className={[
          'pointer-events-none absolute left-1/2 top-1/2 z-[3] -translate-x-1/2 -translate-y-1/2 transition-opacity duration-150',
          picked ? 'opacity-0' : 'opacity-100',
        ].join(' ')}
      >
        <span className="sign flex h-11 w-11 items-center justify-center rounded-full bg-ink text-[0.6rem] text-chalk ring-2 ring-chalk md:h-14 md:w-14 md:text-xs">
          Or
        </span>
      </div>
    </div>
  )
}
