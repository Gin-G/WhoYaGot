#!/usr/bin/env python3
"""League catalogue — drives the tab bar in the UI."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.models import Player
from database.session import get_db
from schemas import LeagueOut
from services.sources import all_sources

router = APIRouter()


@router.get("", response_model=list[LeagueOut])
def leagues(db: Session = Depends(get_db)):
    """Every registered league, with how many players are in its pool.

    `available` is false for a league that is registered but not yet synced, so
    the UI can show the tab greyed out instead of hiding it.
    """
    out = []
    for source in all_sources():
        count = (
            db.query(Player)
            .filter(Player.league == source.league, Player.active.is_(True))
            .count()
        )
        out.append(
            LeagueOut(
                key=source.league,
                name=source.display_name,
                positions=source.positions,
                player_count=count,
                available=count >= 2,
            )
        )
    return out
