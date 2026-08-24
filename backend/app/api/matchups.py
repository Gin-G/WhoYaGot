#!/usr/bin/env python3
"""Deal matchups and record votes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.utils import get_session_id, team_map, vote_count, voter_identity
from database.models import Matchup, Player, PlayerRating, User, Vote
from database.session import get_db
from schemas import MatchupOut, SkipIn, VoteIn, VoteOut, to_card
from services import elo
from services.matchmaking import NoMatchupAvailable, create_matchup
from services.security import current_user_optional

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize(db: Session, matchup: Matchup, a: Player, b: Player) -> MatchupOut:
    teams = team_map(db, matchup.league)
    ratings = {
        r.player_id: r
        for r in db.query(PlayerRating).filter(PlayerRating.player_id.in_([a.id, b.id])).all()
    }
    return MatchupOut(
        id=matchup.id,
        league=matchup.league,
        position=matchup.position,
        player_a=to_card(a, teams.get(a.team_abbr), ratings.get(a.id)),
        player_b=to_card(b, teams.get(b.team_abbr), ratings.get(b.id)),
    )


# What the client sends when it wants no position filter at all, as opposed to
# saying nothing and leaving the answered matchup's own position to stand in.
MIX = "mix"


def _follow_up_position(requested: Optional[str], answered: Optional[str]) -> Optional[str]:
    """Which position the next pair should come from.

    The voter's own filter decides it, not the pair they were just dealt. In
    mixed play a same-position pair still comes up half the time, and reusing
    its position would pin the rest of the session to whichever one that was —
    which is exactly why the mix never mixed.
    """
    if requested is None:
        return answered
    return None if requested.lower() == MIX else requested


def _deal(
    db: Session,
    league: str,
    position: Optional[str],
    user_id: Optional[int],
    session_id: Optional[str],
) -> MatchupOut:
    matchup, a, b = create_matchup(
        db, league=league, position=position, user_id=user_id, session_id=session_id
    )
    db.commit()
    return _serialize(db, matchup, a, b)


@router.get("/next", response_model=MatchupOut)
def next_matchup(
    league: str = Query("nfl"),
    position: Optional[str] = Query(
        None, description="Omit to draw from every position, crossing them freely"
    ),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Serve the next pair to vote on."""
    user_id, session_id = voter_identity(user, session_id)
    try:
        return _deal(db, league.lower(), position, user_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NoMatchupAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/vote", response_model=VoteOut)
def cast_vote(
    payload: VoteIn,
    with_next: bool = Query(True, alias="next", description="Include the following matchup"),
    next_position: Optional[str] = Query(
        None,
        description=(
            "What the following matchup should be drawn from: a position, or "
            "'mix' for no filter. Omitted, the answered matchup's own position "
            "is reused — which is what clients predating this expect."
        ),
    ),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Record a pick and update both the global and personal Elo ladders."""
    matchup = db.get(Matchup, payload.matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="unknown matchup")
    if matchup.answered:
        raise HTTPException(status_code=409, detail="this matchup was already voted on")

    if payload.winner_id == matchup.player_a_id:
        winner_id, loser_id = matchup.player_a_id, matchup.player_b_id
    elif payload.winner_id == matchup.player_b_id:
        winner_id, loser_id = matchup.player_b_id, matchup.player_a_id
    else:
        raise HTTPException(status_code=400, detail="winner is not part of this matchup")

    winner = db.get(Player, winner_id)
    loser = db.get(Player, loser_id)
    if winner is None or loser is None:
        raise HTTPException(status_code=404, detail="matchup references a missing player")

    # Attribute to whoever is voting now, not whoever the matchup was dealt to —
    # someone may have signed in between being served the pair and answering it.
    user_id, session_id = voter_identity(user, session_id)

    ratings = elo.record_result(db, winner, loser, user_id=user_id)

    pick = Vote(
        matchup_id=matchup.id,
        league=matchup.league,
        position=matchup.position,
        winner_id=winner.id,
        loser_id=loser.id,
        user_id=user_id,
        session_id=session_id,
    )
    db.add(pick)
    matchup.answered = True
    db.commit()

    following = None
    if with_next:
        try:
            following = _deal(
                db,
                matchup.league,
                _follow_up_position(next_position, matchup.position),
                user_id,
                session_id,
            )
        except (NoMatchupAvailable, ValueError) as exc:
            # The vote is already saved; the client can retry /next on its own.
            logger.warning("could not deal follow-up matchup: %s", exc)

    agrees = (
        db.query(Vote)
        .filter(Vote.winner_id == winner.id, Vote.loser_id == loser.id)
        .count()
    )
    differs = (
        db.query(Vote)
        .filter(Vote.winner_id == loser.id, Vote.loser_id == winner.id)
        .count()
    )

    return VoteOut(
        recorded=True,
        pick_id=pick.id,
        league=matchup.league,
        position=matchup.position,
        winner_id=winner.id,
        loser_id=loser.id,
        ratings=ratings,
        total_votes=vote_count(db, user_id, session_id),
        crowd_agrees=agrees,
        crowd_differs=differs,
        next=following,
    )


@router.post("/skip", response_model=MatchupOut)
def skip_matchup(
    payload: SkipIn,
    next_position: Optional[str] = Query(
        None, description="Same meaning as on /vote: a position, or 'mix' for no filter"
    ),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Pass on a pair without rating anyone, and get another."""
    matchup = db.get(Matchup, payload.matchup_id)
    if matchup is None:
        raise HTTPException(status_code=404, detail="unknown matchup")

    user_id, session_id = voter_identity(user, session_id)
    try:
        return _deal(
            db,
            matchup.league,
            _follow_up_position(next_position, matchup.position),
            user_id,
            session_id,
        )
    except NoMatchupAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
