#!/usr/bin/env python3
"""
Google Sign-In verification and app session tokens.

The client (web or Android) does the Google flow itself and hands us the
resulting ID token. We verify that token against Google's public keys, then mint
our own short JWT — so every later request is one local signature check with no
round trip to Google.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy.orm import Session

from config import GOOGLE_CLIENT_IDS, JWT_ALGORITHM, JWT_SECRET, JWT_TTL_DAYS
from database.models import User, utcnow
from database.session import get_db

logger = logging.getLogger(__name__)

_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


class AuthError(Exception):
    pass


def verify_google_token(credential: str) -> dict:
    """Verify a Google ID token and return its claims.

    Audience is checked here rather than by the library because web and Android
    builds use different OAuth client IDs, and either is acceptable.
    """
    if not GOOGLE_CLIENT_IDS:
        raise AuthError("GOOGLE_CLIENT_IDS is not configured on the server")

    try:
        claims = google_id_token.verify_oauth2_token(
            credential, google_requests.Request(), audience=None
        )
    except ValueError as exc:
        raise AuthError(f"invalid Google token: {exc}") from exc

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise AuthError("token was not issued by Google")

    if claims.get("aud") not in GOOGLE_CLIENT_IDS:
        raise AuthError("token was issued for a different application")

    if not claims.get("sub"):
        raise AuthError("token has no subject claim")

    return claims


def upsert_user(db: Session, claims: dict) -> User:
    """Find or create the user behind a set of verified Google claims."""
    google_sub = claims["sub"]
    user = db.query(User).filter(User.google_sub == google_sub).one_or_none()

    if user is None:
        user = User(google_sub=google_sub)
        db.add(user)

    # Refresh the profile every sign-in; people change names and avatars. Only
    # where the token actually says so, though: clients differ in which claims
    # they include, and a sign-in from a thinner one must not blank a profile
    # that a richer one already filled in.
    if claims.get("email"):
        user.email = claims["email"]
    if claims.get("name") or claims.get("email"):
        user.name = claims.get("name") or claims.get("email")
    if claims.get("picture"):
        user.picture = claims["picture"]
    user.last_seen_at = utcnow()

    db.flush()
    return user


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "iat": now,
        "exp": now + timedelta(days=JWT_TTL_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError(f"invalid session token: {exc}") from exc


def _bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def current_user_optional(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """The signed-in user, or None. Anonymous voting depends on this."""
    token = _bearer(authorization)
    if not token:
        return None
    try:
        claims = _decode(token)
        return db.get(User, int(claims["sub"]))
    except (AuthError, KeyError, ValueError):
        # A stale or malformed token should not lock someone out of voting.
        return None


def current_user(user: Optional[User] = Depends(current_user_optional)) -> User:
    """The signed-in user. 401s if there isn't one."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="sign in required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
