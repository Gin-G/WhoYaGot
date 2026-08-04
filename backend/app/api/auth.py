#!/usr/bin/env python3
"""Google Sign-In."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.utils import get_session_id, vote_count
from database.models import Matchup, Player, User, UserPlayerRating, Vote
from database.session import get_db
from schemas import AuthOut, GoogleAuthIn, UserOut
from services import elo
from services.security import (
    AuthError,
    create_access_token,
    current_user,
    upsert_user,
    verify_google_token,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _claim_session_votes(db: Session, user: User, session_id: str) -> int:
    """Move a pre-login session's votes onto the account.

    The global ladder already counted these votes, so only the user's personal
    ladder is replayed here — in chronological order, since Elo is path
    dependent. Votes on players the user has already rated are merged in rather
    than reset.
    """
    votes = (
        db.query(Vote)
        .filter(Vote.session_id == session_id, Vote.user_id.is_(None))
        .order_by(Vote.created_at.asc())
        .all()
    )
    if not votes:
        return 0

    for vote in votes:
        winner = db.get(Player, vote.winner_id)
        loser = db.get(Player, vote.loser_id)
        if winner is None or loser is None:
            continue

        # Personal ladder only — replaying the global one would double count.
        elo.record_personal_result(db, user.id, winner, loser)

        vote.user_id = user.id
        vote.session_id = None

    db.query(Matchup).filter(
        Matchup.session_id == session_id, Matchup.user_id.is_(None)
    ).update({"user_id": user.id, "session_id": None}, synchronize_session=False)

    return len(votes)


@router.post("/google", response_model=AuthOut)
def google_sign_in(
    payload: GoogleAuthIn,
    db: Session = Depends(get_db),
    header_session_id: Optional[str] = Depends(get_session_id),
):
    """Exchange a Google ID token for a WhoYaGot session token."""
    try:
        claims = verify_google_token(payload.credential)
    except AuthError as exc:
        logger.warning("google sign-in rejected: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))

    user = upsert_user(db, claims)

    claimed = 0
    session_id = payload.session_id or header_session_id
    if session_id:
        claimed = _claim_session_votes(db, user, session_id)

    db.commit()

    return AuthOut(
        access_token=create_access_token(user),
        user=UserOut(
            id=user.id,
            email=user.email,
            name=user.name,
            picture=user.picture,
            vote_count=vote_count(db, user.id, None),
        ),
        votes_claimed=claimed,
    )


@router.get("/me", response_model=UserOut)
def me(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        picture=user.picture,
        vote_count=vote_count(db, user.id, None),
    )


@router.delete("/me/votes")
def reset_my_list(db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Clear the user's personal ladder. Global ratings keep their votes."""
    removed = (
        db.query(UserPlayerRating).filter(UserPlayerRating.user_id == user.id).delete()
    )
    db.commit()
    return {"status": "success", "players_reset": removed}
