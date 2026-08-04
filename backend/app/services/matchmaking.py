#!/usr/bin/env python3
"""
Pairing logic: same position, Elo-weighted.

Two goals pull against each other. Ratings converge fastest when opponents are
closely matched, but every player needs enough votes for their rating to mean
anything. So the first player is drawn with a bias toward the under-voted, and
the second is drawn from those rated near it — widening the window until
something eligible turns up.

Pools are one position in one league (~60-200 players), so the whole pool is
loaded and sampled in Python rather than pushed into SQL.
"""

import logging
import random
import uuid
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.models import Matchup, Player, PlayerRating, Vote
from services.sources import get_source

logger = logging.getLogger(__name__)

# Rating windows tried in order, in Elo points. None means "anyone left".
RATING_WINDOWS = (75.0, 150.0, 300.0, None)

# How many of the least-voted players count as "needs coverage".
COVERAGE_POOL = 25
COVERAGE_BIAS = 0.5

# Anchors tried before conceding a pair the voter has already seen.
ANCHOR_ATTEMPTS = 6

# Pairs the voter has already seen are avoided until they have seen most of the
# position, at which point repeats are allowed rather than returning nothing.
MAX_HISTORY = 500


class NoMatchupAvailable(RuntimeError):
    pass


def _pool(db: Session, league: str, position: str) -> list[tuple[Player, PlayerRating]]:
    return (
        db.query(Player, PlayerRating)
        .join(PlayerRating, PlayerRating.player_id == Player.id)
        .filter(
            Player.league == league,
            Player.position == position,
            Player.active.is_(True),
        )
        .all()
    )


def _seen_opponents(
    db: Session,
    player_id: int,
    user_id: Optional[int],
    session_id: Optional[str],
) -> set[int]:
    """Player IDs this voter has already judged against `player_id`."""
    if user_id is None and session_id is None:
        return set()

    q = db.query(Vote.winner_id, Vote.loser_id).filter(
        or_(Vote.winner_id == player_id, Vote.loser_id == player_id)
    )
    q = q.filter(Vote.user_id == user_id) if user_id is not None else q.filter(
        Vote.session_id == session_id
    )

    opponents = set()
    for winner_id, loser_id in q.order_by(Vote.created_at.desc()).limit(MAX_HISTORY):
        opponents.add(loser_id if winner_id == player_id else winner_id)
    return opponents


def _pick_anchor(pool: list[tuple[Player, PlayerRating]]) -> tuple[Player, PlayerRating]:
    if random.random() < COVERAGE_BIAS:
        under_voted = sorted(pool, key=lambda pr: pr[1].votes)[:COVERAGE_POOL]
        return random.choice(under_voted)
    return random.choice(pool)


def _pick_opponent(
    anchor: tuple[Player, PlayerRating],
    pool: list[tuple[Player, PlayerRating]],
    exclude: set[int],
    allow_repeat: bool,
) -> Optional[tuple[Player, PlayerRating]]:
    anchor_player, anchor_rating = anchor
    others = [pr for pr in pool if pr[0].id != anchor_player.id]

    for window in RATING_WINDOWS:
        candidates = [pr for pr in others if pr[0].id not in exclude]
        if window is not None:
            candidates = [
                pr for pr in candidates if abs(pr[1].rating - anchor_rating.rating) <= window
            ]
        if candidates:
            return random.choice(candidates)

    # This player has been judged against everyone already. Prefer to go find a
    # different anchor; only repeat a pair once that has also failed.
    if allow_repeat and others:
        return random.choice(others)
    return None


def choose_position(league: str, position: Optional[str]) -> str:
    source = get_source(league)
    if position:
        position = position.upper()
        if position not in source.positions:
            raise ValueError(
                f"{position} is not a votable position in {league} "
                f"(have: {', '.join(source.positions)})"
            )
        return position
    return random.choice(source.positions)


def create_matchup(
    db: Session,
    league: str,
    position: Optional[str] = None,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> tuple[Matchup, Player, Player]:
    """Deal one pair and persist it. Caller commits."""
    position = choose_position(league, position)
    pool = _pool(db, league, position)

    if len(pool) < 2:
        raise NoMatchupAvailable(
            f"need at least 2 active {position}s in {league}, found {len(pool)} "
            "— run the player sync"
        )

    # A heavily-voted player can run out of opponents the voter has not already
    # judged them against. Try other anchors before giving in to a repeat.
    anchor = opponent = None
    for attempt in range(ANCHOR_ATTEMPTS):
        anchor = _pick_anchor(pool)
        exclude = _seen_opponents(db, anchor[0].id, user_id, session_id)
        opponent = _pick_opponent(
            anchor, pool, exclude, allow_repeat=attempt == ANCHOR_ATTEMPTS - 1
        )
        if opponent is not None:
            break

    if anchor is None or opponent is None:
        raise NoMatchupAvailable(f"no eligible opponent in {league} {position}")

    # Randomise side so the anchor is not always on the left.
    a, b = (anchor[0], opponent[0]) if random.random() < 0.5 else (opponent[0], anchor[0])

    matchup = Matchup(
        id=uuid.uuid4().hex,
        league=league,
        position=position,
        player_a_id=a.id,
        player_b_id=b.id,
        user_id=user_id,
        session_id=session_id,
    )
    db.add(matchup)
    return matchup, a, b
