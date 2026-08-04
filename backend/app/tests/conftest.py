import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.models import Base, Player, PlayerRating, Team  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def make_pool(db):
    """Build an NFL pool of `size` quarterbacks, all at the base rating."""

    def _make(size: int = 8):
        db.merge(Team(league="nfl", abbr="BUF", name="Buffalo Bills", color="#00338D"))
        players = []
        for i in range(size):
            player = Player(
                league="nfl",
                external_id=f"00-{i:04d}",
                name=f"Test Player{i}",
                position="QB",
                team_abbr="BUF",
                active=True,
            )
            db.add(player)
            players.append(player)
        db.flush()
        for player in players:
            db.add(PlayerRating(player_id=player.id, league="nfl", position="QB", rating=1500.0))
        db.commit()
        return players

    return _make


@pytest.fixture()
def pool(make_pool):
    return make_pool(8)
