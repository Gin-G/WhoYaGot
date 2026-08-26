#!/usr/bin/env python3
"""Shared router helpers."""

from typing import Optional

from fastapi import Header
from sqlalchemy.orm import Session

from database.models import Team, User, Vote


def get_session_id(x_session_id: Optional[str] = Header(None)) -> Optional[str]:
    """Anonymous voter ID, generated client-side and kept in local storage.

    Lets someone vote before signing in; those votes are claimed by their
    account the first time they authenticate with the same session ID.
    """
    return x_session_id


def owned_by(q, user_id: Optional[int], session_id: Optional[str]):
    """Narrow a vote query to the voter asking. Never trust an ID alone."""
    if user_id is not None:
        return q.filter(Vote.user_id == user_id)
    return q.filter(Vote.session_id == session_id)


def team_map(db: Session, league: str) -> dict[str, Team]:
    return {t.abbr: t for t in db.query(Team).filter(Team.league == league).all()}


def voter_identity(
    user: Optional[User], session_id: Optional[str]
) -> tuple[Optional[int], Optional[str]]:
    """Signed-in users are tracked by ID; everyone else by session."""
    if user is not None:
        return user.id, None
    return None, session_id


def vote_count(db: Session, user_id: Optional[int], session_id: Optional[str]) -> int:
    if user_id is not None:
        return db.query(Vote).filter(Vote.user_id == user_id).count()
    if session_id:
        return db.query(Vote).filter(Vote.session_id == session_id).count()
    return 0
