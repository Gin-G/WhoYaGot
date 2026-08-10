#!/usr/bin/env python3
"""
Pairing logic: same position, Elo-weighted.

Only the players who will actually see the field are dealt: an offseason roster
runs 90 deep per team and most of that is camp bodies, so each position is cut
to its best-projected `pool_depth` before anything else happens.

From there two goals pull against each other. Ratings converge fastest when
opponents are closely matched, but every player needs enough votes for their
rating to mean anything. So the first player is drawn with a bias toward the
under-voted, and the second is drawn from those rated near it — widening the
window until something eligible turns up.

Coverage alone leaves a voter with a list of undefeated players who never met
each other, so once they have voted enough to have a list worth sorting, a share
of matchups is drawn from players they have already ranked instead.

Pools are one position in one league (~50-150 players), so the whole pool is
loaded and sampled in Python rather than pushed into SQL.
"""

import logging
import random
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from database.models import Matchup, Player, PlayerRating, UserPlayerRating, Vote
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

# Share of matchups drawn from players the voter has already ranked, and how
# many votes they need at a position before that kicks in. Below the threshold
# there is no list to sort yet; above it, an all-coverage diet would leave the
# top of their list a pile of unbeaten players who never faced each other.
RANKED_PAIR_RATE = 0.25
RANKED_PAIR_MIN_VOTES = 20

# How far apart in the voter's own list a consolidation pair may sit. Neighbours
# are the ones whose order is still genuinely unsettled; pitting their #1
# against their #40 tells us nothing we don't already know.
RANKED_PAIR_SPAN = 4


class NoMatchupAvailable(RuntimeError):
    pass


def _pool(db: Session, league: str, position: str) -> list[tuple[Player, PlayerRating]]:
    """The players worth voting on at this position.

    An offseason roster is 90 deep and most of it never takes a snap, so the
    pool is the `pool_depth` players most likely to be on the field rather than
    everyone with a jersey. Players below the cut keep any rating they have
    already earned — they just stop being dealt.
    """
    q = (
        db.query(Player, PlayerRating)
        .join(PlayerRating, PlayerRating.player_id == Player.id)
        .filter(
            Player.league == league,
            Player.position == position,
            Player.active.is_(True),
        )
    )

    depth = get_source(league).pool_depth.get(position)
    if depth:
        ranked = (
            q.filter(Player.usage.isnot(None))
            .order_by(Player.usage.desc())
            .limit(depth)
            .all()
        )
        # A season can have rosters published before anyone has projected it,
        # and a deployment that has not re-synced since this arrived scores
        # nobody. Neither is a reason to stop dealing matchups.
        if len(ranked) >= 2:
            return ranked
        logger.warning(
            "%s %s: nobody scored — dealing from the full roster instead",
            league,
            position,
        )

    return q.all()


def _history(
    db: Session,
    league: str,
    position: str,
    user_id: Optional[int],
    session_id: Optional[str],
) -> list[tuple[int, int]]:
    """Every pair this voter has already judged at this position, newest first."""
    if user_id is None and session_id is None:
        return []

    q = db.query(Vote.winner_id, Vote.loser_id).filter(
        Vote.league == league, Vote.position == position
    )
    q = q.filter(Vote.user_id == user_id) if user_id is not None else q.filter(
        Vote.session_id == session_id
    )
    return [
        (winner_id, loser_id)
        for winner_id, loser_id in q.order_by(Vote.created_at.desc()).limit(MAX_HISTORY)
    ]


def _seen_opponents(history: list[tuple[int, int]], player_id: int) -> set[int]:
    """Player IDs the voter has already judged against `player_id`."""
    return {
        loser_id if winner_id == player_id else winner_id
        for winner_id, loser_id in history
        if player_id in (winner_id, loser_id)
    }


def _voter_ratings(
    db: Session, league: str, position: str, user_id: Optional[int]
) -> dict[int, float]:
    """The voter's own Elo — the ordering a consolidation pair tries to settle."""
    if user_id is None:
        return {}

    rows = db.query(UserPlayerRating.player_id, UserPlayerRating.rating).filter(
        UserPlayerRating.user_id == user_id,
        UserPlayerRating.league == league,
        UserPlayerRating.position == position,
    )
    return dict(rows)


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


def _pick_ranked_pair(
    pool: list[tuple[Player, PlayerRating]],
    history: list[tuple[int, int]],
    ratings: dict[int, float],
) -> Optional[tuple[tuple[Player, PlayerRating], tuple[Player, PlayerRating]]]:
    """Two already-ranked players sitting near each other in the voter's list,
    favouring the top of it.

    Anonymous voters have no ladder of their own, so the global rating stands in
    as the ordering — still a better guess at which pairs are unsettled than
    drawing from the ranked set at random.
    """
    ranked = {player_id for pair in history for player_id in pair}
    candidates = [pr for pr in pool if pr[0].id in ranked]
    if len(candidates) < 3:
        return None

    candidates.sort(key=lambda pr: ratings.get(pr[0].id, pr[1].rating), reverse=True)
    seen = {frozenset(pair) for pair in history}

    # Weighted toward the top, because a list is read from the top and drawing
    # evenly over 150 ranked players would barely touch the leaders — who are
    # precisely the ones sitting undefeated for want of having played each other.
    neighbours, weights = [], []
    for i in range(len(candidates)):
        for j in range(i + 1, min(i + 1 + RANKED_PAIR_SPAN, len(candidates))):
            if frozenset({candidates[i][0].id, candidates[j][0].id}) in seen:
                continue
            neighbours.append((candidates[i], candidates[j]))
            weights.append(1.0 / (i + 1))

    # Every neighbouring pair has been judged already; the caller's normal draw
    # will bring in someone new instead.
    return random.choices(neighbours, weights)[0] if neighbours else None


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

    history = _history(db, league, position, user_id, session_id)

    anchor = opponent = None
    if len(history) >= RANKED_PAIR_MIN_VOTES and random.random() < RANKED_PAIR_RATE:
        pair = _pick_ranked_pair(
            pool, history, _voter_ratings(db, league, position, user_id)
        )
        if pair is not None:
            anchor, opponent = pair

    # A heavily-voted player can run out of opponents the voter has not already
    # judged them against. Try other anchors before giving in to a repeat.
    if opponent is None:
        for attempt in range(ANCHOR_ATTEMPTS):
            anchor = _pick_anchor(pool)
            exclude = _seen_opponents(history, anchor[0].id)
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
