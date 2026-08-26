#!/usr/bin/env python3
"""Deal matchups and record votes."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from api.utils import get_session_id, owned_by, team_map, vote_count, voter_identity
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


def _dial(first: Optional[int], last: Optional[int]) -> Optional[tuple[int, int]]:
    """A rank range to work on, or None for the ordinary draw.

    Both ends or neither: half a range is an ambiguous request, and guessing
    which half was meant would quietly deal from somewhere the voter did not
    ask for.
    """
    if first is None and last is None:
        return None
    if first is None or last is None:
        raise HTTPException(
            status_code=400,
            detail="dial_from and dial_to go together — send both or neither",
        )
    if first < 1 or last < 1:
        raise HTTPException(status_code=400, detail="ranks start at 1")
    return (min(first, last), max(first, last))


def _deal(
    db: Session,
    league: str,
    position: Optional[str],
    user_id: Optional[int],
    session_id: Optional[str],
    dial: Optional[tuple[int, int]] = None,
) -> MatchupOut:
    matchup, a, b = create_matchup(
        db,
        league=league,
        position=position,
        user_id=user_id,
        session_id=session_id,
        dial=dial,
    )
    db.commit()
    return _serialize(db, matchup, a, b)


@router.get("/next", response_model=MatchupOut)
def next_matchup(
    league: str = Query("nfl"),
    position: Optional[str] = Query(
        None, description="Omit to draw from every position, crossing them freely"
    ),
    dial_from: Optional[int] = Query(
        None,
        description=(
            "First rank of the stretch of your board to settle. The draw reaches "
            "past both ends of it, since a range cannot be settled against itself"
        ),
    ),
    dial_to: Optional[int] = Query(None, description="Last rank of that stretch"),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(current_user_optional),
    session_id: Optional[str] = Depends(get_session_id),
):
    """Serve the next pair to vote on."""
    user_id, session_id = voter_identity(user, session_id)
    try:
        return _deal(
            db, league.lower(), position, user_id, session_id, _dial(dial_from, dial_to)
        )
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
    dial_from: Optional[int] = Query(
        None, description="Carry a dialled-in range onto the following pair"
    ),
    dial_to: Optional[int] = Query(None, description="Last rank of that stretch"),
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

    before = elo.snapshot(db, winner, loser, user_id=user_id)

    # An answer replaces the last one on the same pair rather than joining it.
    # A board is what the voter thinks now: take Coleman over Boutte in August
    # and Boutte over Coleman in September and only one of those is an opinion,
    # the other is a thing they used to believe. Averaging the two would report
    # neither, and leaving both on record puts the pair in contradiction with
    # itself — which reads on the board as a knot nothing can settle, when in
    # fact the voter is perfectly clear.
    superseded = owned_by(
        db.query(Vote).filter(
            Vote.league == matchup.league,
            or_(
                and_(Vote.winner_id == winner.id, Vote.loser_id == loser.id),
                and_(Vote.winner_id == loser.id, Vote.loser_id == winner.id),
            ),
        ),
        user_id,
        session_id,
    ).all()
    for old_pick in superseded:
        db.delete(old_pick)

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

    if superseded:
        # Ratings carry the replaced answer inside them, and no single update
        # can take it back out — the ladder has to be rebuilt from what stands.
        db.flush()
        elo.replay(db, matchup.league)
        if user_id is not None:
            elo.replay(db, matchup.league, user_id=user_id)
        ratings = elo.movement_since(db, winner, loser, before, user_id=user_id)
    else:
        ratings = elo.record_result(db, winner, loser, user_id=user_id)
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
                _dial(dial_from, dial_to),
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
    dial_from: Optional[int] = Query(
        None, description="Carry a dialled-in range onto the following pair"
    ),
    dial_to: Optional[int] = Query(None, description="Last rank of that stretch"),
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
            _dial(dial_from, dial_to),
        )
    except NoMatchupAvailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
