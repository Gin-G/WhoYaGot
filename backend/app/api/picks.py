#!/usr/bin/env python3
"""
The picks a voter has made: look them up, take one back, or change your mind.

A board built over a training camp is not a board built in one sitting. What
looked right in August is worth revisiting in September, and a pick made too
fast is worth taking back — so votes are readable, reversible, and revisable
rather than write-once.

Every change here rebuilds ratings from the surviving votes instead of trying
to subtract what the old one did. See `elo.replay` for why that is the only
answer that is actually correct.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.utils import get_session_id, team_map, voter_identity
from database.models import Matchup, Player, PlayerRating, User, Vote
from database.session import get_db
from schemas import PickOut, PicksOut, RevisePickIn, to_card
from services import elo
from services.security import current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


def _owned_by(q, user_id: Optional[int], session_id: Optional[str]):
    """Narrow a vote query to the voter asking. Never trust an ID alone."""
    if user_id is not None:
        return q.filter(Vote.user_id == user_id)
    return q.filter(Vote.session_id == session_id)


def _serialize(db: Session, votes: list[Vote]) -> list[PickOut]:
    ids = {v.winner_id for v in votes} | {v.loser_id for v in votes}
    players = {p.id: p for p in db.query(Player).filter(Player.id.in_(ids)).all()} if ids else {}
    ratings = {
        r.player_id: r
        for r in db.query(PlayerRating).filter(PlayerRating.player_id.in_(ids)).all()
    } if ids else {}
    teams = {league: team_map(db, league) for league in {v.league for v in votes}}

    picks = []
    for vote in votes:
        winner, loser = players.get(vote.winner_id), players.get(vote.loser_id)
        if winner is None or loser is None:
            continue
        by_abbr = teams.get(vote.league, {})
        picks.append(
            PickOut(
                id=vote.id,
                league=vote.league,
                position=vote.position,
                created_at=vote.created_at,
                winner=to_card(winner, by_abbr.get(winner.team_abbr), ratings.get(winner.id)),
                loser=to_card(loser, by_abbr.get(loser.team_abbr), ratings.get(loser.id)),
            )
        )
    return picks


def _list_picks(
    db: Session,
    league: str,
    user_id: Optional[int],
    session_id: Optional[str],
    position: Optional[str] = None,
    player_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
) -> PicksOut:
    """The query behind the endpoint, callable without FastAPI's defaults.

    A route function called from another route gets `Query(...)` objects where
    its arguments should be, so the shared work lives here instead.
    """
    league = league.lower()
    if user_id is None and session_id is None:
        return PicksOut(league=league, total=0, picks=[])

    q = _owned_by(db.query(Vote).filter(Vote.league == league), user_id, session_id)
    if position:
        q = q.filter(Vote.position == position.upper())
    if player_id is not None:
        q = q.filter(or_(Vote.winner_id == player_id, Vote.loser_id == player_id))

    total = q.count()
    votes = (
        q.order_by(Vote.created_at.desc(), Vote.id.desc()).offset(offset).limit(limit).all()
    )

    return PicksOut(
        league=league,
        position=position.upper() if position else None,
        player_id=player_id,
        total=total,
        picks=_serialize(db, votes),
    )


@router.get("", response_model=PicksOut)
def my_picks(
    league: str = Query("nfl"),
    position: Optional[str] = Query(None),
    player_id: Optional[int] = Query(
        None, description="Only picks this player was part of, won or lost"
    ),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Your picks, newest first.

    `player_id` answers the question you actually ask when a player looks
    misplaced: who have I put him up against, and how did I call each one?
    """
    user_id, session_id = voter_identity(user, session_id)
    return _list_picks(
        db, league, user_id, session_id, position, player_id, limit=limit, offset=offset
    )


def _load_own_vote(
    db: Session, vote_id: int, user_id: Optional[int], session_id: Optional[str]
) -> Vote:
    if user_id is None and session_id is None:
        raise HTTPException(status_code=401, detail="no voter to attribute this to")

    vote = _owned_by(db.query(Vote).filter(Vote.id == vote_id), user_id, session_id).first()
    if vote is None:
        # Deliberately the same answer whether the pick belongs to someone else
        # or does not exist. Which one it is, is not the asker's business.
        raise HTTPException(status_code=404, detail="no such pick of yours")
    return vote


def _rebuild(db: Session, league: str, user_id: Optional[int]) -> None:
    """Replay the crowd's ladder, and the voter's own if they are signed in."""
    elo.replay(db, league)
    if user_id is not None:
        elo.replay(db, league, user_id=user_id)


@router.delete("/player/{player_id}", response_model=PicksOut)
def reset_player(
    player_id: int,
    league: str = Query("nfl"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Take back every pick this player was part of, and start him over.

    A board is a record of what was true when it was built. A hamstring in the
    third preseason week does not just move a player down it — it makes every
    answer already given about him an answer to a question nobody is asking any
    more. He was taken over thirty others as a starter, and each of those picks
    is still holding him up.

    So this drops them rather than adjusting them. He falls back under the vote
    threshold, off the board, and returns to the pool to be asked about again
    from nothing.

    Everyone else keeps their own picks, but the board can still move under
    them: his picks were evidence about his opponents too, and a player whose
    place rested mainly on beating him can fall under the threshold himself and
    drop off alongside. That is the honest result rather than a side effect —
    what was known about him was known through a player who has changed.

    The pairs go back on the table too, so the matchmaker is free to deal them
    again — which is the point, because the answers will be different now.
    """
    league = league.lower()
    user_id, session_id = voter_identity(user, session_id)
    if user_id is None and session_id is None:
        raise HTTPException(status_code=401, detail="no voter to attribute this to")

    if db.get(Player, player_id) is None:
        raise HTTPException(status_code=404, detail="unknown player")

    votes = _owned_by(
        db.query(Vote).filter(
            Vote.league == league,
            or_(Vote.winner_id == player_id, Vote.loser_id == player_id),
        ),
        user_id,
        session_id,
    ).all()

    for vote in votes:
        matchup = db.get(Matchup, vote.matchup_id)
        if matchup is not None:
            matchup.answered = False
        db.delete(vote)

    if votes:
        db.flush()
        _rebuild(db, league, user_id)
    db.commit()

    logger.info("reset player %s in %s: %d picks taken back", player_id, league, len(votes))
    return _list_picks(db, league, user_id, session_id)


@router.delete("/{vote_id}", response_model=PicksOut)
def undo_pick(
    vote_id: int,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Take a pick back as though it had never been made."""
    user_id, session_id = voter_identity(user, session_id)
    vote = _load_own_vote(db, vote_id, user_id, session_id)
    league = vote.league

    # Put the matchup back on the table. It was marked answered by a pick that
    # no longer exists, and the pair deserves to come round again.
    matchup = db.get(Matchup, vote.matchup_id)
    if matchup is not None:
        matchup.answered = False

    db.delete(vote)
    db.flush()
    _rebuild(db, league, user_id)
    db.commit()

    logger.info("undid pick %s in %s", vote_id, league)
    return _list_picks(db, league, user_id, session_id)


@router.patch("/{vote_id}", response_model=PicksOut)
def revise_pick(
    vote_id: int,
    payload: RevisePickIn,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Change your mind about who won, keeping the pair and its place in time."""
    user_id, session_id = voter_identity(user, session_id)
    vote = _load_own_vote(db, vote_id, user_id, session_id)

    if payload.winner_id not in (vote.winner_id, vote.loser_id):
        raise HTTPException(status_code=400, detail="that player was not in this pick")

    if payload.winner_id != vote.winner_id:
        vote.winner_id, vote.loser_id = vote.loser_id, vote.winner_id
        db.flush()
        _rebuild(db, vote.league, user_id)

    db.commit()
    return _list_picks(db, vote.league, user_id, session_id)
