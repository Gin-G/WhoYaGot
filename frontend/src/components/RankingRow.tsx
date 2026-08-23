import { Link } from 'react-router-dom'

import type { RankingEntry } from '../api/types'

/**
 * How far you have a player from where the crowd has him.
 *
 * Only ever drawn on your own board, and only once the crowd can place him.
 * A dash rather than a zero when you agree: agreement is the common case, and
 * a column of green zeros would read as movement.
 */
function VersusCrowd({ places }: { places?: number | null }) {
  if (places === null || places === undefined) return null

  const agreed = places === 0
  const size = Math.abs(places)
  const described = agreed
    ? 'Same as the overall list'
    : `${size} ${size === 1 ? 'place' : 'places'} ${
        places > 0 ? 'higher' : 'lower'
      } than the overall list`

  return (
    <span
      title={described}
      className={[
        'tabular flex w-10 shrink-0 items-center justify-end gap-0.5 text-[0.68rem] font-semibold',
        agreed ? 'text-ink-soft/50' : places > 0 ? 'text-verdict-up' : 'text-verdict-down',
      ].join(' ')}
    >
      {/* The glyphs read as punctuation aloud, and a bare "2" says nothing. */}
      <span className="sr-only">{described}</span>
      <span aria-hidden>{agreed ? '–' : places > 0 ? `▲${size}` : `▼${size}`}</span>
    </span>
  )
}

/**
 * Rank strip, tote-board style: the number leads, the data is monospace.
 *
 * On your own board the name links to the picks that put him there — when
 * someone looks misplaced, the next question is always what he beat.
 */
export function RankingRow({ entry, showPicks = false }: { entry: RankingEntry; showPicks?: boolean }) {
  const { rank, player, locked } = entry
  const rating = player.rating
  const team = player.team

  return (
    /* A settled place gets the whole row, not just the number. Colouring four
       digits green among two hundred black ones is a difference you have to go
       looking for; a block of colour is one you can see from the top of the
       list, which is the point — the eye should find the settled stretch of a
       board without reading it. */
    <li
      className={[
        'flex items-center gap-3 border-b border-ink/12 py-2.5 pl-1 pr-3 md:gap-4',
        locked ? 'bg-settled' : '',
      ].join(' ')}
      title={locked ? `Rank ${rank} is settled — your picks put him here` : undefined}
    >
      <span
        className="tabular w-9 shrink-0 text-right text-lg font-semibold text-ink md:w-12 md:text-2xl"
        aria-label={locked ? `Rank ${rank}, settled by your picks` : `Rank ${rank}`}
      >
        {rank}
      </span>

      {/* Team color as a rule, not a swatch — it identifies without shouting. */}
      <span
        aria-hidden
        className="h-9 w-1 shrink-0 md:h-11"
        style={{ background: team?.color ?? '#3A4046' }}
      />

      {player.headshot_url && (
        <img
          src={player.headshot_url}
          alt=""
          aria-hidden
          loading="lazy"
          className="h-9 w-9 shrink-0 object-contain md:h-11 md:w-11"
        />
      )}

      <div className="min-w-0 flex-1">
        {showPicks ? (
          <Link
            to={`/picks?player=${player.id}`}
            title={`Every pick ${player.name} was part of`}
            className="sign-tight block truncate text-[0.8rem] text-ink hover:underline md:text-sm"
          >
            {player.name}
          </Link>
        ) : (
          <div className="sign-tight truncate text-[0.8rem] text-ink md:text-sm">{player.name}</div>
        )}
        <div className="tabular truncate text-[0.65rem] uppercase tracking-wider text-ink-soft">
          {[team?.abbr, player.position, player.jersey_number ? `#${player.jersey_number}` : null]
            .filter(Boolean)
            .join('  ·  ')}
        </div>
      </div>

      {team?.logo_url && (
        <img src={team.logo_url} alt="" aria-hidden className="hidden h-7 w-7 shrink-0 sm:block" />
      )}

      <VersusCrowd places={entry.versus_crowd} />

      {rating && (
        <div className="shrink-0 text-right">
          <div className="tabular text-sm font-semibold text-ink md:text-base">
            {Math.round(rating.rating)}
          </div>
          <div className="tabular text-[0.6rem] uppercase tracking-wider text-ink-soft">
            {rating.wins}–{rating.losses}
          </div>
        </div>
      )}
    </li>
  )
}
