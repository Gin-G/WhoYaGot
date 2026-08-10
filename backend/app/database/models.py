#!/usr/bin/env python3
"""
SQLAlchemy models for WhoYaGot.

Everything is keyed by `league` from the start so adding MLB/NHL/NBA/soccer/golf
is a matter of registering another source adapter, not a schema migration.
Player identity is (league, external_id) — the ID the upstream source uses, e.g.
an nflverse gsis_id like "00-0034796".
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    league = Column(String, primary_key=True)
    abbr = Column(String, primary_key=True)

    name = Column(String)
    conference = Column(String)
    division = Column(String)
    color = Column(String)
    color2 = Column(String)
    logo_url = Column(String)
    wordmark_url = Column(String)

    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class Player(Base):
    __tablename__ = "players"

    id = Column(Integer, primary_key=True, autoincrement=True)
    league = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False)

    name = Column(String, nullable=False)
    position = Column(String, index=True)
    team_abbr = Column(String, index=True)
    jersey_number = Column(Integer)
    headshot_url = Column(String)

    # Card-back detail. Nullable because not every league's source supplies them.
    height = Column(String)
    weight = Column(Float)
    college = Column(String)
    years_exp = Column(Integer)
    draft_year = Column(Integer)
    draft_number = Column(Integer)
    birth_date = Column(String)

    # Only active players enter the matchup pool. Sync flips this rather than
    # deleting, so historical votes always resolve to a real player.
    active = Column(Boolean, default=True, nullable=False, index=True)
    season = Column(Integer)

    # How much this player is expected to be on the field: the better of what
    # the source projects for him and what he actually did last season.
    # Offseason rosters run 90 deep and most of those players never take a snap,
    # so this is what separates the league from the camp bodies. The scale is
    # whatever the source uses (fantasy points for the NFL) and is only ever
    # compared within a position — never across positions or leagues. NULL means
    # the source knows nothing about him, which is not the same as a zero.
    #
    # Unindexed on purpose: it is only ever read behind ix_player_pool, which
    # narrows to a few hundred rows before this is sorted.
    usage = Column(Float)

    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    rating = relationship(
        "PlayerRating", back_populates="player", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("league", "external_id", name="uq_player_league_external"),
        Index("ix_player_pool", "league", "position", "active"),
    )


class PlayerRating(Base):
    """Global Elo, aggregated across every user's votes."""

    __tablename__ = "player_ratings"

    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    league = Column(String, nullable=False, index=True)
    position = Column(String, index=True)

    rating = Column(Float, nullable=False, default=1500.0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    votes = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    player = relationship("Player", back_populates="rating")

    __table_args__ = (Index("ix_rating_leaderboard", "league", "position", "rating"),)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    google_sub = Column(String, nullable=False, unique=True, index=True)
    email = Column(String, index=True)
    name = Column(String)
    picture = Column(String)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_seen_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class UserPlayerRating(Base):
    """Per-user Elo — this is what "your list" is built from."""

    __tablename__ = "user_player_ratings"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    league = Column(String, nullable=False)
    position = Column(String)

    rating = Column(Float, nullable=False, default=1500.0)
    wins = Column(Integer, nullable=False, default=0)
    losses = Column(Integer, nullable=False, default=0)
    votes = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_user_list", "user_id", "league", "position", "rating"),)


class Matchup(Base):
    """A pair the server dealt out.

    Votes reference a matchup rather than naming two arbitrary player IDs, so a
    client can only vote on a pair the server actually offered, and a matchup
    that is served but never answered is still visible as a skip.
    """

    __tablename__ = "matchups"

    id = Column(String, primary_key=True)  # uuid4 hex
    league = Column(String, nullable=False, index=True)
    position = Column(String, index=True)

    player_a_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    player_b_id = Column(Integer, ForeignKey("players.id"), nullable=False)

    # Exactly one of these identifies the voter: user_id once signed in,
    # session_id for anonymous voting before sign-in.
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    session_id = Column(String, index=True)

    created_at = Column(DateTime, default=utcnow, nullable=False)
    answered = Column(Boolean, default=False, nullable=False)


class Vote(Base):
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    matchup_id = Column(String, ForeignKey("matchups.id"), nullable=False, unique=True)

    league = Column(String, nullable=False, index=True)
    position = Column(String, index=True)
    winner_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)
    loser_id = Column(Integer, ForeignKey("players.id"), nullable=False, index=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True)
    session_id = Column(String, index=True)

    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)

    __table_args__ = (Index("ix_vote_pair", "winner_id", "loser_id"),)
