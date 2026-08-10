#!/usr/bin/env python3
"""
Elo ratings.

Two independent ladders share this math: a global one aggregating every user's
votes, and a per-user one that produces "your list". A vote updates both.

K falls as a player accumulates votes so early results move fast and settled
ratings stay stable.
"""

from typing import Optional

from sqlalchemy.orm import Session

from config import ELO_BASE
from database.models import Player, PlayerRating, UserPlayerRating, Vote


def k_factor(votes: int) -> float:
    if votes < 20:
        return 40.0
    if votes < 80:
        return 24.0
    return 12.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability A beats B."""
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))


def _apply(winner, loser) -> tuple[float, float]:
    """Update a winner/loser rating pair in place. Returns the deltas."""
    exp_w = expected_score(winner.rating, loser.rating)
    exp_l = 1.0 - exp_w

    delta_w = k_factor(winner.votes) * (1.0 - exp_w)
    delta_l = k_factor(loser.votes) * (0.0 - exp_l)

    winner.rating += delta_w
    loser.rating += delta_l

    winner.wins += 1
    winner.votes += 1
    loser.losses += 1
    loser.votes += 1

    return delta_w, delta_l


def _get_global(db: Session, player: Player) -> PlayerRating:
    rating = db.get(PlayerRating, player.id)
    if rating is None:
        rating = PlayerRating(
            player_id=player.id,
            league=player.league,
            position=player.position,
            rating=ELO_BASE,
        )
        db.add(rating)
        db.flush()
    return rating


def _get_user(db: Session, user_id: int, player: Player) -> UserPlayerRating:
    rating = db.get(UserPlayerRating, (user_id, player.id))
    if rating is None:
        rating = UserPlayerRating(
            user_id=user_id,
            player_id=player.id,
            league=player.league,
            position=player.position,
            rating=ELO_BASE,
        )
        db.add(rating)
        db.flush()
    return rating


def record_personal_result(db: Session, user_id: int, winner: Player, loser: Player) -> None:
    """Apply a vote to one user's ladder only.

    Used when replaying anonymous votes onto an account at sign-in: the global
    ladder already counted them, so only the personal one needs to catch up.
    """
    _apply(_get_user(db, user_id, winner), _get_user(db, user_id, loser))


def replay(db: Session, league: str, user_id: Optional[int] = None) -> int:
    """Rebuild ratings from the votes that survive, in the order they were cast.

    Elo is path-dependent: every rating a vote produces is the input to the next
    one, so a vote that is removed or reversed cannot be unwound by subtracting
    what it did. The rating it moved has since been used to price a dozen other
    matchups. The only exact answer is to play the sequence again.

    Costs one pass over the league's votes — a few hundred at this scale, and
    cheap enough that correctness is not worth trading for. If a league ever
    reaches the point where this is felt, store the per-vote deltas and unwind
    the tail instead of the whole history.

    Pass `user_id` to rebuild one person's ladder, or omit it for the global
    one. Caller commits.
    """
    votes = (
        db.query(Vote)
        .filter(Vote.league == league)
        .order_by(Vote.created_at.asc(), Vote.id.asc())
    )

    if user_id is None:
        # Reset in place rather than deleting: the sync seeds a rating row for
        # every active player, and the matchup pool is an inner join onto them.
        # Dropping the rows would empty the pool of everyone yet to be voted on.
        db.query(PlayerRating).filter(PlayerRating.league == league).update(
            {"rating": ELO_BASE, "wins": 0, "losses": 0, "votes": 0}
        )
    else:
        votes = votes.filter(Vote.user_id == user_id)
        db.query(UserPlayerRating).filter(
            UserPlayerRating.user_id == user_id, UserPlayerRating.league == league
        ).delete()
    db.flush()

    replayed = 0
    for vote in votes.all():
        winner = db.get(Player, vote.winner_id)
        loser = db.get(Player, vote.loser_id)
        # A player deleted outright would take their votes with them, but a
        # missing one here must not abort the rebuild of everyone else.
        if winner is None or loser is None:
            continue
        if user_id is None:
            _apply(_get_global(db, winner), _get_global(db, loser))
        else:
            _apply(_get_user(db, user_id, winner), _get_user(db, user_id, loser))
        replayed += 1

    return replayed


def record_result(
    db: Session,
    winner: Player,
    loser: Player,
    user_id: Optional[int] = None,
) -> dict:
    """Apply one vote to the global ladder, and the user's ladder if signed in.

    Caller commits.
    """
    g_win = _get_global(db, winner)
    g_lose = _get_global(db, loser)
    delta_w, delta_l = _apply(g_win, g_lose)

    result = {
        "global": {
            "winner": {"rating": round(g_win.rating, 1), "delta": round(delta_w, 1)},
            "loser": {"rating": round(g_lose.rating, 1), "delta": round(delta_l, 1)},
        }
    }

    if user_id is not None:
        u_win = _get_user(db, user_id, winner)
        u_lose = _get_user(db, user_id, loser)
        u_delta_w, u_delta_l = _apply(u_win, u_lose)
        result["personal"] = {
            "winner": {"rating": round(u_win.rating, 1), "delta": round(u_delta_w, 1)},
            "loser": {"rating": round(u_lose.rating, 1), "delta": round(u_delta_l, 1)},
        }

    return result
