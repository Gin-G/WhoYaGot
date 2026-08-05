#!/usr/bin/env python3
"""
Pull a league's teams and players from its source into the local DB.

Idempotent: re-running updates rows in place. Players who drop off the roster
are deactivated rather than deleted, so old votes still resolve to a real player
and their rating survives if they come back.
"""

import logging
from dataclasses import asdict
from typing import Optional

from sqlalchemy.orm import Session

from config import ELO_BASE
from database.models import Player, PlayerRating, Team
from services.sources import get_source
from services.sources.base import SourceUnavailable

logger = logging.getLogger(__name__)

_PLAYER_FIELDS = (
    "name",
    "position",
    "team_abbr",
    "headshot_url",
    "jersey_number",
    "height",
    "weight",
    "college",
    "years_exp",
    "draft_year",
    "draft_number",
    "birth_date",
    "season",
)


def sync_teams(db: Session, league: str) -> int:
    source = get_source(league)
    existing = {t.abbr: t for t in db.query(Team).filter(Team.league == league).all()}

    for st in source.fetch_teams():
        team = existing.get(st.abbr)
        if team is None:
            team = Team(league=league, abbr=st.abbr)
            db.add(team)
        for key, value in asdict(st).items():
            if key != "abbr":
                setattr(team, key, value)

    db.commit()
    return len(existing)


def sync_players(db: Session, league: str, season: Optional[int] = None) -> dict:
    source = get_source(league)
    fetched = source.fetch_players(season=season)

    existing = {p.external_id: p for p in db.query(Player).filter(Player.league == league).all()}

    # Every player absent from the fetch gets deactivated below, so an empty
    # fetch would empty the pool and leave matchmaking with nothing to deal.
    # A league never loses its entire roster; the source is having a bad day.
    active_before = sum(1 for p in existing.values() if p.active)
    if not fetched and active_before:
        raise SourceUnavailable(
            f"{league}: source returned no players — refusing to deactivate "
            f"the {active_before} already in the pool"
        )

    seen: set[str] = set()
    created = 0

    for sp in fetched:
        # Guard against a source handing back the same player twice — the
        # unique constraint would otherwise abort the whole sync.
        if sp.external_id in seen:
            logger.warning("%s: duplicate external_id %s (%s), skipping", league, sp.external_id, sp.name)
            continue
        seen.add(sp.external_id)
        player = existing.get(sp.external_id)
        if player is None:
            player = Player(league=league, external_id=sp.external_id)
            db.add(player)
            created += 1
        for key in _PLAYER_FIELDS:
            setattr(player, key, getattr(sp, key))
        player.active = True

    deactivated = 0
    for external_id, player in existing.items():
        if external_id not in seen and player.active:
            player.active = False
            deactivated += 1

    # Flush so newly-added players get their IDs before we seed rating rows.
    db.flush()

    rated = {r.player_id for r in db.query(PlayerRating.player_id).filter(PlayerRating.league == league).all()}
    seeded = 0
    for player in db.query(Player).filter(Player.league == league, Player.active.is_(True)).all():
        if player.id in rated:
            continue
        db.add(
            PlayerRating(
                player_id=player.id,
                league=league,
                position=player.position,
                rating=ELO_BASE,
            )
        )
        seeded += 1

    db.commit()

    result = {
        "league": league,
        # Which season the pool now reflects. Worth reporting: the source picks
        # this when the caller does not, and a silently stale one is invisible.
        "season": fetched[0].season if fetched else None,
        "fetched": len(fetched),
        "created": created,
        "updated": len(fetched) - created,
        "deactivated": deactivated,
        "ratings_seeded": seeded,
    }
    logger.info("sync complete: %s", result)
    return result


def sync_league(db: Session, league: str, season: Optional[int] = None) -> dict:
    sync_teams(db, league)
    return sync_players(db, league, season=season)
