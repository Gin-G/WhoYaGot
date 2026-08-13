#!/usr/bin/env python3
"""
Pairing logic: Elo-weighted, within a position or across them.

Only the players who will actually see the field are dealt: an offseason roster
runs 90 deep per team and most of that is camp bodies, so each position is cut
to its best-projected `pool_depth` before anything else happens.

Pin a position and you get that position. Leave it open and half the matchups
cross positions — Gibbs or Chase, Allen or Wilson — because that is the question
a single ranking has to answer, and four ladders that never touch cannot.

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
# pool, at which point repeats are allowed rather than returning nothing. Read
# across the whole league, not one position, because a pair is a pair.
MAX_HISTORY = 2000

# Share of matchups that cross positions when the voter has not pinned one.
CROSS_POSITION_RATE = 0.5

# Share of matchups drawn from the draftable core rather than the wider pool.
# The pool is who might play; the core is who anyone would draft. Ranking the
# fringe against the fringe produces an answer nobody wanted the question to.
# The remainder is not waste: it is how a player outside the core gets the
# chance to show he belongs in it, which a hard cut would never allow.
CORE_RATE = 0.85

# How far apart in their own positions' pecking orders a cross-position pair may
# sit, as a fraction of the position, widened until something turns up.
#
# Standing rather than rating, because the four ladders have not met and their
# scales have not converged: TE has a fraction of the votes QB does, so its best
# player sits at 1577 where the best QB is at 1646. Pairing on the raw number
# would put the best tight end in the league against a middling quarterback.
# Pairing on standing asks the question actually worth asking — the best of one
# against the best of another — and stays right once the scales do merge.
STANDING_WINDOWS = (0.06, 0.15, 0.30, None)

# Votes at which a player's rating is trusted as much as his projection when
# working out that standing. Low, because a handful of results at one position
# already says more about the order than a model does.
STANDING_TRUST_VOTES = 4

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


def _position_pool(
    db: Session, league: str, position: str, depth: Optional[int]
) -> list[tuple[Player, PlayerRating]]:
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


def _pool(
    db: Session, league: str, positions: list[str], depths: dict[str, int]
) -> list[tuple[Player, PlayerRating]]:
    """Every position's cut, put together. One position in means one pool out."""
    pool = []
    for position in positions:
        pool.extend(_position_pool(db, league, position, depths.get(position)))
    return pool


def _core_ids(
    pool: list[tuple[Player, PlayerRating]], depths: dict[str, int]
) -> set[int]:
    """Who inside the pool anyone would actually draft.

    Taken out of the pool rather than queried separately, so the core is always
    a subset of what is eligible and the two cannot drift apart. A position with
    no depth declared contributes all of itself, which is what makes this a
    no-op for a league that has not drawn the distinction.
    """
    if not depths:
        return {player.id for player, _ in pool}

    by_position: dict[str, list[tuple[Player, PlayerRating]]] = {}
    for entry in pool:
        by_position.setdefault(entry[0].position, []).append(entry)

    ids = set()
    for position, group in by_position.items():
        depth = depths.get(position)
        # Nothing scored means nothing to rank a core by. The pool falls back to
        # the whole roster in that case and so must this, or the "core" would be
        # whichever players the database happened to return first.
        if not depth or not any(player.usage is not None for player, _ in group):
            ids.update(player.id for player, _ in group)
            continue
        group = sorted(group, key=lambda pr: -(pr[0].usage or 0.0))
        ids.update(player.id for player, _ in group[:depth])
    return ids


def _standing(pool: list[tuple[Player, PlayerRating]]) -> dict[int, float]:
    """Where each player sits in his own position, 0.0 best and 1.0 worst.

    Two readings of that, blended by how much the first is worth. Where the
    pecking order is voted in, it is the voter's own; where it is not, it is
    what the player is projected to do.

    Neither alone survives contact with a real board. Rating alone is noise
    exactly where it is needed most — tight ends average barely one vote each,
    so a backup who won his only matchup outranks a starter nobody has been
    dealt yet. Projection alone would pair on a model's opinion and ignore
    everything the voter has said. So a player's rating is trusted in
    proportion to the votes behind it, and the projection covers the rest.
    """
    standing: dict[int, float] = {}
    by_position: dict[str, list[tuple[Player, PlayerRating]]] = {}
    for entry in pool:
        by_position.setdefault(entry[0].position, []).append(entry)

    for group in by_position.values():
        last = max(len(group) - 1, 1)
        by_rating = {
            player.id: place
            for place, (player, _) in enumerate(
                sorted(group, key=lambda pr: -pr[1].rating)
            )
        }
        by_usage = {
            player.id: place
            for place, (player, _) in enumerate(
                sorted(group, key=lambda pr: -(pr[0].usage or 0.0))
            )
        }

        for player, rating in group:
            trust = rating.votes / (rating.votes + STANDING_TRUST_VOTES)
            place = trust * by_rating[player.id] + (1 - trust) * by_usage[player.id]
            standing[player.id] = place / last

    return standing


def _history(
    db: Session,
    league: str,
    user_id: Optional[int],
    session_id: Optional[str],
) -> list[tuple[int, int]]:
    """Every pair this voter has already judged in this league, newest first."""
    if user_id is None and session_id is None:
        return []

    q = db.query(Vote.winner_id, Vote.loser_id).filter(Vote.league == league)
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


def _voter_ratings(db: Session, league: str, user_id: Optional[int]) -> dict[int, float]:
    """The voter's own Elo — the ordering a consolidation pair tries to settle."""
    if user_id is None:
        return {}

    rows = db.query(UserPlayerRating.player_id, UserPlayerRating.rating).filter(
        UserPlayerRating.user_id == user_id,
        UserPlayerRating.league == league,
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


def _pick_across_positions(
    anchor: tuple[Player, PlayerRating],
    pool: list[tuple[Player, PlayerRating]],
    standing: dict[int, float],
    exclude: set[int],
    allow_repeat: bool,
) -> Optional[tuple[Player, PlayerRating]]:
    """An opponent from a different position, of comparable standing in his own.

    The best running back against the best receiver is a question worth asking.
    The best running back against the fortieth receiver is not.
    """
    anchor_player = anchor[0]
    anchor_standing = standing.get(anchor_player.id, 0.5)
    others = [pr for pr in pool if pr[0].position != anchor_player.position]

    for window in STANDING_WINDOWS:
        candidates = [pr for pr in others if pr[0].id not in exclude]
        if window is not None:
            candidates = [
                pr
                for pr in candidates
                if abs(standing.get(pr[0].id, 0.5) - anchor_standing) <= window
            ]
        if candidates:
            return random.choice(candidates)

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
    """Deal one pair and persist it. Caller commits.

    A pinned position is honoured exactly. Left open, the deal crosses positions
    a share of the time — and the matchup it stores has no position of its own,
    because it does not belong to one.
    """
    source = get_source(league)
    # Asking for a position is asking for that position; only an open request
    # is free to cross.
    across = position is None and random.random() < CROSS_POSITION_RATE
    positions = source.positions if across else [choose_position(league, position)]

    wide = _pool(db, league, positions, source.pool_depth)
    wanted = "any position" if across else positions[0]

    if len(wide) < 2:
        raise NoMatchupAvailable(
            f"need at least 2 active players in {league} {wanted}, found {len(wide)} "
            "— run the player sync"
        )

    # Nearly every matchup is core against core. The rest is not the same draw
    # over a bigger pool — that would mostly turn up two core players again and
    # waste the slot. It is anchored on someone outside the core deliberately,
    # so the one chance a fringe player gets is a real one, against whoever sits
    # nearest him.
    core_ids = _core_ids(wide, source.core_depth)
    if random.random() < CORE_RATE:
        pool = anchors = [pr for pr in wide if pr[0].id in core_ids]
    else:
        pool = wide
        anchors = [pr for pr in wide if pr[0].id not in core_ids] or wide

    history = _history(db, league, user_id, session_id)

    anchor = opponent = None
    if len(history) >= RANKED_PAIR_MIN_VOTES and random.random() < RANKED_PAIR_RATE:
        pair = _pick_ranked_pair(pool, history, _voter_ratings(db, league, user_id))
        if pair is not None:
            anchor, opponent = pair

    # A heavily-voted player can run out of opponents the voter has not already
    # judged them against. Try other anchors before giving in to a repeat.
    if opponent is None:
        standing = _standing(pool) if across else {}
        for attempt in range(ANCHOR_ATTEMPTS):
            anchor = _pick_anchor(anchors)
            exclude = _seen_opponents(history, anchor[0].id)
            last_try = attempt == ANCHOR_ATTEMPTS - 1
            opponent = (
                _pick_across_positions(anchor, pool, standing, exclude, last_try)
                if across
                else _pick_opponent(anchor, pool, exclude, allow_repeat=last_try)
            )
            if opponent is not None:
                break

    if anchor is None or opponent is None:
        raise NoMatchupAvailable(f"no eligible opponent in {league} {wanted}")

    # Randomise side so the anchor is not always on the left.
    a, b = (anchor[0], opponent[0]) if random.random() < 0.5 else (opponent[0], anchor[0])

    matchup = Matchup(
        id=uuid.uuid4().hex,
        league=league,
        # No position when the pair crosses them: the matchup belongs to the
        # league, and a follow-up dealt from it should be free to cross again.
        position=None if a.position != b.position else a.position,
        player_a_id=a.id,
        player_b_id=b.id,
        user_id=user_id,
        session_id=session_id,
    )
    db.add(matchup)
    return matchup, a, b
