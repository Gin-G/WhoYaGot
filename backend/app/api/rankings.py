#!/usr/bin/env python3
"""Leaderboards: the crowd's list, and each user's own."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.utils import team_map
from database.models import Player, PlayerRating, User, UserPlayerRating
from database.session import get_db
from schemas import RankingEntry, RankingsOut, to_card
from services.security import current_user

router = APIRouter()

# A rating built from two votes is noise. Hide players below this on the global
# board (their rating still exists and still moves — it just isn't ranked yet).
MIN_VOTES_GLOBAL = 5

# The same idea for one person's board, at a threshold their own voting can
# actually reach: a personal ladder is fed by one voter rather than all of them,
# so the global bar would leave a new board empty for hundreds of picks.
MIN_VOTES_PERSONAL = 3


@router.get("", response_model=RankingsOut)
def rankings(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_votes: int = Query(MIN_VOTES_GLOBAL, ge=0),
    db: Session = Depends(get_db),
):
    """The overall list, across every user's votes."""
    league = league.lower()

    q = (
        db.query(Player, PlayerRating)
        .join(PlayerRating, PlayerRating.player_id == Player.id)
        .filter(Player.league == league, Player.active.is_(True))
        .filter(PlayerRating.votes >= min_votes)
    )
    if position:
        q = q.filter(Player.position == position.upper())

    total = q.count()
    rows = q.order_by(PlayerRating.rating.desc()).offset(offset).limit(limit).all()
    teams = team_map(db, league)

    return RankingsOut(
        league=league,
        position=position.upper() if position else None,
        scope="global",
        total=total,
        entries=[
            RankingEntry(
                rank=offset + i + 1,
                player=to_card(player, teams.get(player.team_abbr), rating),
            )
            for i, (player, rating) in enumerate(rows)
        ],
    )


@router.get("/me", response_model=RankingsOut)
def my_rankings(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    min_votes: int = Query(MIN_VOTES_PERSONAL, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """The signed-in user's own list, from their votes alone."""
    league = league.lower()

    q = (
        db.query(Player, UserPlayerRating)
        .join(UserPlayerRating, UserPlayerRating.player_id == Player.id)
        .filter(UserPlayerRating.user_id == user.id, UserPlayerRating.league == league)
        .filter(UserPlayerRating.votes >= min_votes)
    )
    if position:
        q = q.filter(Player.position == position.upper())

    total = q.count()
    rows = q.order_by(UserPlayerRating.rating.desc()).offset(offset).limit(limit).all()
    teams = team_map(db, league)

    return RankingsOut(
        league=league,
        position=position.upper() if position else None,
        scope="personal",
        total=total,
        entries=[
            RankingEntry(
                rank=offset + i + 1,
                player=to_card(player, teams.get(player.team_abbr), rating),
            )
            for i, (player, rating) in enumerate(rows)
        ],
    )


@router.get("/head-to-head")
def head_to_head(
    player_a: int = Query(..., description="Player ID"),
    player_b: int = Query(..., description="Player ID"),
    db: Session = Depends(get_db),
):
    """How the crowd has split on one specific pairing."""
    from database.models import Vote

    a = db.get(Player, player_a)
    b = db.get(Player, player_b)
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="unknown player")

    a_wins = (
        db.query(Vote).filter(Vote.winner_id == player_a, Vote.loser_id == player_b).count()
    )
    b_wins = (
        db.query(Vote).filter(Vote.winner_id == player_b, Vote.loser_id == player_a).count()
    )
    total = a_wins + b_wins

    return {
        "player_a": {"id": a.id, "name": a.name, "wins": a_wins},
        "player_b": {"id": b.id, "name": b.name, "wins": b_wins},
        "total_votes": total,
        "player_a_pct": round(a_wins / total, 3) if total else None,
    }
