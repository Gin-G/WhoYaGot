/**
 * Your board, in the shape each destination wants to be handed it.
 *
 * Every site takes the list in rank order — what differs is whether it wants a
 * paste or a file, and how much it wants beside the name. Adding a site means
 * adding an entry here; nothing else in the app knows the formats exist.
 *
 * MFL is the one written from its own import screen ("You may type or paste
 * player names, one per line", accepting "First Last" or "Last, First"). The
 * CSV destinations below are built to the common denominator their uploaders
 * document — a header row, one player per row, order carrying the ranking —
 * rather than a published column spec, since neither publishes one. If a site
 * rejects a file, the fix is a column change here.
 */

import type { RankingEntry } from '../api/types'
import { lastFirst } from './playerName'

export interface ExportFormat {
  key: string
  /** Chip text. The destination, since that is what someone is scanning for. */
  label: string
  /** Where this goes and what to do with it, once it is on the clipboard. */
  hint: string
  extension: 'txt' | 'csv'
  build: (entries: RankingEntry[]) => string
}

type Cell = string | number | null | undefined

/** Quote only when the value would otherwise break the row. */
function cell(value: Cell): string {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function csv(header: string[], rows: Cell[][]): string {
  return [header, ...rows].map((row) => row.map(cell).join(',')).join('\n') + '\n'
}

/** Rank, name, team, position — the columns every uploader looks for. */
function rankedRows(entries: RankingEntry[]): Cell[][] {
  return entries.map((entry) => [
    entry.rank,
    entry.player.name,
    entry.player.team?.abbr,
    entry.player.position,
  ])
}

export const EXPORT_FORMATS: ExportFormat[] = [
  {
    key: 'mfl',
    label: 'MyFantasyLeague',
    hint: 'Paste into "My Draft List". One name per line, "First Last" — which is also the safe paste for any site not listed here.',
    extension: 'txt',
    build: (entries) => entries.map((entry) => entry.player.name).join('\n'),
  },
  {
    key: 'mfl-surname',
    label: 'MFL · Last, First',
    hint: 'The same list in the other order MFL accepts. Worth trying when a name comes back unmatched.',
    extension: 'txt',
    build: (entries) => entries.map((entry) => lastFirst(entry.player.name)).join('\n'),
  },
  {
    key: 'yahoo',
    label: 'Yahoo',
    hint: 'Download it, then upload the file under Pre-Draft Rankings. Yahoo matches on the player column and keeps your row order.',
    extension: 'csv',
    build: (entries) => csv(['Rank', 'Player', 'Team', 'Position'], rankedRows(entries)),
  },
  {
    key: 'drafters',
    label: 'Drafters',
    hint: 'Download it, then use CSV Upload on the rankings page. Your row order becomes the draft queue.',
    extension: 'csv',
    build: (entries) => csv(['Rank', 'Player', 'Team', 'Position'], rankedRows(entries)),
  },
  {
    key: 'sheet',
    label: 'Spreadsheet',
    hint: 'The whole board with ratings, records and your gap to the crowd — for your own sheet rather than an import.',
    extension: 'csv',
    build: (entries) =>
      csv(
        ['Rank', 'Player', 'Team', 'Position', 'Rating', 'W', 'L', 'Vs Crowd'],
        entries.map((entry) => [
          entry.rank,
          entry.player.name,
          entry.player.team?.abbr,
          entry.player.position,
          entry.player.rating ? Math.round(entry.player.rating.rating) : '',
          entry.player.rating?.wins,
          entry.player.rating?.losses,
          entry.versus_crowd ?? '',
        ]),
      ),
  },
]

export function formatFor(key: string): ExportFormat {
  return EXPORT_FORMATS.find((format) => format.key === key) ?? EXPORT_FORMATS[0]
}
