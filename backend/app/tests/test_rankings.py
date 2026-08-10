"""The boards are plain functions, so they are called directly rather than over HTTP."""

from api.rankings import MIN_VOTES_PERSONAL, my_rankings, rankings
from database.models import PlayerRating, User, UserPlayerRating


def _board(db, user, **kwargs):
    params = {
        "league": "nfl",
        "position": None,
        "limit": 50,
        "offset": 0,
        "min_votes": MIN_VOTES_PERSONAL,
        "db": db,
        "user": user,
    }
    return my_rankings(**{**params, **kwargs})


def _rate(db, user, player, votes, rating):
    db.add(
        UserPlayerRating(
            user_id=user.id,
            player_id=player.id,
            league="nfl",
            position="QB",
            rating=rating,
            wins=votes,
            votes=votes,
        )
    )
    db.commit()


def _user(db):
    user = User(google_sub="sub-1")
    db.add(user)
    db.commit()
    return user


def test_a_player_judged_once_is_not_yet_ranked(db, pool):
    """One win should not outrank the rest of the league on your own board."""
    user = _user(db)
    _rate(db, user, pool[0], votes=1, rating=1520.0)
    _rate(db, user, pool[1], votes=MIN_VOTES_PERSONAL, rating=1510.0)

    board = _board(db, user)

    assert [e.player.id for e in board.entries] == [pool[1].id]
    assert board.total == 1


def test_the_floor_can_be_lowered_by_the_caller(db, pool):
    user = _user(db)
    _rate(db, user, pool[0], votes=1, rating=1520.0)

    assert _board(db, user, min_votes=0).total == 1
    assert _board(db, user).total == 0


def test_ranks_are_numbered_after_the_floor_is_applied(db, pool):
    user = _user(db)
    _rate(db, user, pool[0], votes=1, rating=1600.0)
    for i, player in enumerate(pool[1:4]):
        _rate(db, user, player, votes=MIN_VOTES_PERSONAL, rating=1550.0 - i)

    board = _board(db, user)

    assert [e.rank for e in board.entries] == [1, 2, 3]
    assert [e.player.id for e in board.entries] == [p.id for p in pool[1:4]]


def test_one_users_board_is_not_filtered_by_anothers_votes(db, pool):
    user = _user(db)
    other = User(google_sub="sub-2")
    db.add(other)
    db.commit()
    _rate(db, other, pool[0], votes=MIN_VOTES_PERSONAL, rating=1600.0)

    assert _board(db, user).total == 0
    assert _board(db, other).total == 1


def test_the_global_board_keeps_its_own_higher_floor(db, pool):
    """The crowd's board is fed by everyone, so it can afford to ask for more."""
    db.get(PlayerRating, pool[0].id).votes = MIN_VOTES_PERSONAL
    db.commit()

    board = rankings(league="nfl", position=None, limit=50, offset=0, min_votes=5, db=db)

    assert board.total == 0
