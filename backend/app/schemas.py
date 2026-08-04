#!/usr/bin/env python3
"""Pydantic response/request models and the Player -> card serializer."""

from typing import Optional

from pydantic import BaseModel, Field

from database.models import Player, PlayerRating, Team


class TeamOut(BaseModel):
    abbr: str
    name: Optional[str] = None
    conference: Optional[str] = None
    division: Optional[str] = None
    color: Optional[str] = None
    color2: Optional[str] = None
    logo_url: Optional[str] = None
    wordmark_url: Optional[str] = None


class RatingOut(BaseModel):
    rating: float
    wins: int
    losses: int
    votes: int
    win_pct: Optional[float] = None


class PlayerCard(BaseModel):
    id: int
    external_id: str
    league: str
    name: str
    position: Optional[str] = None
    jersey_number: Optional[int] = None
    headshot_url: Optional[str] = None
    height: Optional[str] = None
    weight: Optional[float] = None
    college: Optional[str] = None
    years_exp: Optional[int] = None
    draft_year: Optional[int] = None
    draft_number: Optional[int] = None
    team: Optional[TeamOut] = None
    rating: Optional[RatingOut] = None


class MatchupOut(BaseModel):
    id: str
    league: str
    position: str
    player_a: PlayerCard
    player_b: PlayerCard


class VoteIn(BaseModel):
    matchup_id: str
    winner_id: int


class VoteOut(BaseModel):
    recorded: bool
    league: str
    position: str
    winner_id: int
    loser_id: int
    ratings: dict
    total_votes: int = Field(description="How many votes this voter has cast overall")
    next: Optional[MatchupOut] = None


class SkipIn(BaseModel):
    matchup_id: str


class RankingEntry(BaseModel):
    rank: int
    player: PlayerCard


class RankingsOut(BaseModel):
    league: str
    position: Optional[str] = None
    scope: str
    total: int
    entries: list[RankingEntry]


class LeagueOut(BaseModel):
    key: str
    name: str
    positions: list[str]
    player_count: int
    available: bool


class GoogleAuthIn(BaseModel):
    credential: str = Field(description="Google ID token from Sign In With Google")
    session_id: Optional[str] = Field(
        default=None,
        description="Anonymous session whose votes should be claimed by this account",
    )


class UserOut(BaseModel):
    id: int
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    vote_count: int = 0


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
    votes_claimed: int = 0


def _win_pct(rating: PlayerRating) -> Optional[float]:
    played = rating.wins + rating.losses
    return round(rating.wins / played, 3) if played else None


def to_card(
    player: Player,
    team: Optional[Team] = None,
    rating=None,
) -> PlayerCard:
    """Serialize a player for the UI. `rating` is a PlayerRating or UserPlayerRating."""
    return PlayerCard(
        id=player.id,
        external_id=player.external_id,
        league=player.league,
        name=player.name,
        position=player.position,
        jersey_number=player.jersey_number,
        headshot_url=player.headshot_url,
        height=player.height,
        weight=player.weight,
        college=player.college,
        years_exp=player.years_exp,
        draft_year=player.draft_year,
        draft_number=player.draft_number,
        team=(
            TeamOut(
                abbr=team.abbr,
                name=team.name,
                conference=team.conference,
                division=team.division,
                color=team.color,
                color2=team.color2,
                logo_url=team.logo_url,
                wordmark_url=team.wordmark_url,
            )
            if team
            else (TeamOut(abbr=player.team_abbr) if player.team_abbr else None)
        ),
        rating=(
            RatingOut(
                rating=round(rating.rating, 1),
                wins=rating.wins,
                losses=rating.losses,
                votes=rating.votes,
                win_pct=_win_pct(rating),
            )
            if rating
            else None
        ),
    )
