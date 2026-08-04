import type { PlayerCard } from '../api/types'
import { fieldFor } from '../lib/color'

// Generational suffixes belong with the surname, not billed as one. The league
// is full of them — without this, "Marvin Harrison Jr." reads as a giant "JR."
const SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v'])

/** "Christian McCaffrey" -> given "CHRISTIAN", family "McCAFFREY". */
function splitName(name: string): { given: string; family: string } {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 1) return { given: '', family: parts[0] ?? '' }

  let cut = parts.length - 1
  if (cut > 1 && SUFFIXES.has(parts[cut].toLowerCase())) cut -= 1

  return { given: parts.slice(0, cut).join(' '), family: parts.slice(cut).join(' ') }
}

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
  result?: { rating: number; delta: number } | null
  onPick: () => void
  disabled: boolean
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
          'absolute flex items-center gap-3 px-5 py-4 md:flex-col md:justify-end md:gap-4 md:px-8',
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
            <div className="name-given truncate" style={{ color: dim }}>
              {given}
            </div>
          )}
          <div className="name-family break-words">{family}</div>

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
        </div>
      )}
    </button>
  )
}
