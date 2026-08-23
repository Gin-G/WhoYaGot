export interface Team {
  abbr: string
  name?: string | null
  conference?: string | null
  division?: string | null
  color?: string | null
  color2?: string | null
  logo_url?: string | null
  wordmark_url?: string | null
}

export interface Rating {
  rating: number
  wins: number
  losses: number
  votes: number
  win_pct?: number | null
}

export interface PlayerCard {
  id: number
  external_id: string
  league: string
  name: string
  position?: string | null
  jersey_number?: number | null
  headshot_url?: string | null
  height?: string | null
  weight?: number | null
  college?: string | null
  years_exp?: number | null
  draft_year?: number | null
  draft_number?: number | null
  team?: Team | null
  rating?: Rating | null
}

export interface Matchup {
  id: string
  league: string
  /** Absent when the pair crosses positions. */
  position?: string | null
  player_a: PlayerCard
  player_b: PlayerCard
}

export interface RatingChange {
  rating: number
  delta: number
}

export interface VoteResult {
  recorded: boolean
  /** The pick's own id, so it can be taken back. */
  pick_id: number
  league: string
  position?: string | null
  winner_id: number
  loser_id: number
  ratings: {
    global: { winner: RatingChange; loser: RatingChange }
    personal?: { winner: RatingChange; loser: RatingChange }
  }
  total_votes: number
  next: Matchup | null
}

export interface RankingEntry {
  rank: number
  /** Places above (+) or below (-) where the crowd has him. Null if unrated. */
  versus_crowd?: number | null
  /** Your own picks fix this place: more voting cannot move it. */
  locked?: boolean
  player: PlayerCard
}

export interface Rankings {
  league: string
  position?: string | null
  scope: string
  total: number
  /** Places on the whole board your picks have settled, not just this page. */
  settled?: number
  entries: RankingEntry[]
}

export interface League {
  key: string
  name: string
  positions: string[]
  player_count: number
  available: boolean
}

export interface User {
  id: number
  email?: string | null
  name?: string | null
  picture?: string | null
  vote_count: number
}

export interface AuthResult {
  access_token: string
  token_type: string
  user: User
  votes_claimed: number
}

export interface Pick {
  id: number
  league: string
  position?: string | null
  created_at: string
  winner: PlayerCard
  loser: PlayerCard
}

export interface Picks {
  league: string
  position?: string | null
  player_id?: number | null
  total: number
  picks: Pick[]
}
