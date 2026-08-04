import type { RankingEntry } from '../api/types'

/** Rank strip, tote-board style: the number leads, the data is monospace. */
export function RankingRow({ entry }: { entry: RankingEntry }) {
  const { rank, player } = entry
  const rating = player.rating
  const team = player.team

  return (
    <li className="flex items-center gap-3 border-b border-ink/12 py-2.5 pl-1 pr-3 md:gap-4">
      <span
        className="tabular w-9 shrink-0 text-right text-lg font-semibold text-ink md:w-12 md:text-2xl"
        aria-label={`Rank ${rank}`}
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
        <div className="sign-tight truncate text-[0.8rem] text-ink md:text-sm">{player.name}</div>
        <div className="tabular truncate text-[0.65rem] uppercase tracking-wider text-ink-soft">
          {[team?.abbr, player.position, player.jersey_number ? `#${player.jersey_number}` : null]
            .filter(Boolean)
            .join('  ·  ')}
        </div>
      </div>

      {team?.logo_url && (
        <img src={team.logo_url} alt="" aria-hidden className="hidden h-7 w-7 shrink-0 sm:block" />
      )}

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
