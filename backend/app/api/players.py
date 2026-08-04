#!/usr/bin/env python3
"""Browse and look up players."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.utils import team_map
from database.models import Player, PlayerRating, Team
from database.session import get_db
from schemas import PlayerCard, to_card

router = APIRouter()


@router.get("", response_model=list[PlayerCard])
def list_players(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    team: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Name search"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    league = league.lower()
    query = (
        db.query(Player, PlayerRating)
        .outerjoin(PlayerRating, PlayerRating.player_id == Player.id)
        .filter(Player.league == league, Player.active.is_(True))
    )
    if position:
        query = query.filter(Player.position == position.upper())
    if team:
        query = query.filter(Player.team_abbr == team.upper())
    if q:
        query = query.filter(Player.name.ilike(f"%{q}%"))

    rows = query.order_by(Player.name).offset(offset).limit(limit).all()
    teams = team_map(db, league)
    return [to_card(player, teams.get(player.team_abbr), rating) for player, rating in rows]


@router.get("/{player_id}", response_model=PlayerCard)
def get_player(player_id: int, db: Session = Depends(get_db)):
    player = db.get(Player, player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="unknown player")

    team = db.get(Team, (player.league, player.team_abbr)) if player.team_abbr else None
    return to_card(player, team, db.get(PlayerRating, player.id))
