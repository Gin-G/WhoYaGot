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
  position: string
  player_a: PlayerCard
  player_b: PlayerCard
}

export interface RatingChange {
  rating: number
  delta: number
}

export interface VoteResult {
  recorded: boolean
  league: string
  position: string
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
  player: PlayerCard
}

export interface Rankings {
  league: string
  position?: string | null
  scope: string
  total: number
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
