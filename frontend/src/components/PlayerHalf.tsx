import type { PlayerCard } from '../api/types'
import { fieldFor } from '../lib/color'
import { useFitText } from '../lib/fitText'
import { splitName } from '../lib/playerName'

function heightWeight(player: PlayerCard): string | null {
  const bits: string[] = []
  if (player.height) bits.push(player.height.replace('-', "'") + '"')
  if (player.weight) bits.push(`${Math.round(player.weight)} lb`)
  return bits.length ? bits.join('  ') : null
}

function draftLine(player: PlayerCard): string | null {
  if (!player.draft_year) return null
  const year = `'${String(player.draft_year).slice(-2)}`
  return player.draft_number ? `${year}  PICK ${player.draft_number}` : `${year}  UDFA`
}

interface Props {
  player: PlayerCard
  side: 'a' | 'b'
  /** Overrides the team color when both teams look too similar to tell apart. */
  colorOverride?: string
  state: 'idle' | 'won' | 'lost'
  /** Elo movement, shown only after the pick so it can't sway the vote. */
  result?: { rating: number; delta: number; agrees?: number; differs?: number } | null
  onPick: () => void
  disabled: boolean
}

/**
 * The crowd's record on this pairing, from the perspective of the pick just
 * made. Silent on the first vote a pair has ever had — "100% agree" off one
 * result is a number pretending to be a consensus.
 */
function crowdLine(agrees?: number, differs?: number): string | null {
  if (agrees === undefined || differs === undefined) return null
  const total = agrees + differs
  if (total < 2) return null
  const share = Math.round((agrees / total) * 100)
  return `${share}% agree  ·  ${agrees}\u2013${differs}`
}


export function PlayerHalf({
  player,
  side,
  colorOverride,
  state,
  result,
  onPick,
  disabled,
}: Props) {
  const team = player.team
  const field = fieldFor(colorOverride ?? team?.color, side)
  const { given, family } = splitName(player.name)
  const dim = field.text === '#F5F3EF' ? 'rgba(245,243,239,0.62)' : 'rgba(20,23,26,0.62)'

  // The surname carries the card, so it gets more room to shrink into than the
  // given name above it before either is allowed to clip.
  const givenRef = useFitText<HTMLDivElement>(given, 0.62)
  const familyRef = useFitText<HTMLDivElement>(family, 0.42)

  // Side B mirrors side A so the two halves rotate about the seam rather than
  // repeating — on phones that puts both headshots against the outer edges.
  const mirrored = side === 'b'

  return (
    <button
      type="button"
      onClick={onPick}
      disabled={disabled}
      aria-label={`Pick ${player.name}, ${team?.abbr ?? ''} ${player.position ?? ''}`}
      className={[
        'stage-half',
        side === 'a' ? 'stage-half-a' : 'stage-half-b',
        state === 'won' ? 'stage-half-won' : '',
        state === 'lost' ? 'stage-half-lost' : '',
        'group',
      ].join(' ')}
      style={{ background: field.background, color: field.text }}
    >
      {/* The button fills the stage and is only *visually* clipped, so content
          has to be positioned into this half's own region — otherwise both
          players would lay out around the centre of the whole stage and
          overprint each other. */}
      <div
        className={[
          // Tighter gutters than the desktop layout: on a phone that width is
          // better spent on the name than on margin.
          'absolute flex items-center gap-2 px-3 py-4 md:flex-col md:justify-end md:gap-4 md:px-8',
          side === 'a'
            ? 'left-0 right-0 top-0 h-1/2 md:right-auto md:h-full md:w-1/2'
            : 'bottom-0 left-0 right-0 h-1/2 md:bottom-auto md:left-auto md:right-0 md:top-0 md:h-full md:w-1/2',
          mirrored ? 'flex-row-reverse' : 'flex-row',
          // Keep content clear of the tilted seam.
          side === 'a' ? 'pb-8 md:pb-6 md:pr-16' : 'pt-8 md:pt-6 md:pl-16',
        ].join(' ')}
      >
        {/* Team wordmark, ghosted — texture drawn from the data itself. */}
        {team?.wordmark_url && (
          <img
            src={team.wordmark_url}
            alt=""
            aria-hidden
            className="pointer-events-none absolute left-1/2 top-1/2 w-[120%] max-w-none -translate-x-1/2 -translate-y-1/2 opacity-[0.07]"
          />
        )}

        {/* Anchored to the half's lower edge and bled past it, so the flat
            bottom of the source PNG is cut by the seam rather than floating
            in the middle of the field as a hard rectangle. */}
        {player.headshot_url && (
          <img
            src={player.headshot_url}
            alt=""
            aria-hidden
            loading="eager"
            className="relative -mb-7 h-[clamp(8rem,34vw,13rem)] w-auto shrink-0 self-end object-contain transition-transform duration-300 ease-slam group-hover:scale-[1.04] md:order-2 md:-mb-12 md:h-[clamp(11rem,32vh,20rem)] md:self-center"
          />
        )}

        <div
          className={[
            'relative min-w-0 flex-1 md:order-1 md:flex-none md:text-center',
            mirrored ? 'text-left' : 'text-right',
          ].join(' ')}
        >
          {given && (
            <div ref={givenRef} className="name-given name-fit" style={{ color: dim }}>
              {given}
            </div>
          )}
          <div ref={familyRef} className="name-family name-fit">
            {family}
          </div>

          <div
            className={[
              'mt-3 flex items-center gap-2.5 md:justify-center',
              mirrored ? 'justify-start' : 'justify-end',
            ].join(' ')}
          >
            {team?.logo_url && (
              <img src={team.logo_url} alt="" aria-hidden className="h-7 w-7 md:h-9 md:w-9" />
            )}
            <span className="sign text-[0.7rem] md:text-xs">
              {[team?.abbr, player.position, player.jersey_number ? `#${player.jersey_number}` : null]
                .filter(Boolean)
                .join('  ·  ')}
            </span>
          </div>

          <div
            className="tabular mt-2 hidden text-[0.68rem] uppercase leading-relaxed tracking-wider sm:block"
            style={{ color: dim }}
          >
            {[heightWeight(player), player.college, draftLine(player)].filter(Boolean).join('   ·   ')}
          </div>
        </div>
      </div>

      {/* Elo payoff, revealed on the flood. */}
      {state === 'won' && result && (
        <div
          className="tabular absolute inset-x-0 bottom-[calc(var(--inset-bottom)+1.25rem)] text-center text-sm font-semibold"
          style={{ color: field.text }}
        >
          <span className="rounded-full bg-ink/25 px-3 py-1">
            {result.delta >= 0 ? '+' : ''}
            {result.delta.toFixed(0)} → {result.rating.toFixed(0)}
          </span>
          {/* How the room has called this same pair, and only ever afterwards:
              told beforehand, a voter answers the room instead of the
              question, and the room stops learning anything. */}
          {crowdLine(result.agrees, result.differs) && (
            <div className="mt-1.5 text-[0.62rem] uppercase tracking-wider" style={{ color: dim }}>
              {crowdLine(result.agrees, result.differs)}
            </div>
          )}
        </div>
      )}
    </button>
  )
}
