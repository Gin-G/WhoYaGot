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


def _crowd(db, player, rating, votes=MIN_VOTES_PERSONAL):
    row = db.get(PlayerRating, player.id)
    row.rating, row.votes = rating, votes
    db.commit()


def test_a_player_you_rate_higher_than_the_crowd_reads_as_a_gain(db, pool):
    user = _user(db)
    # Your order: pool[0] then pool[1]. The crowd's: the other way round.
    _rate(db, user, pool[0], votes=5, rating=1600.0)
    _rate(db, user, pool[1], votes=5, rating=1550.0)
    _crowd(db, pool[0], 1400.0)
    _crowd(db, pool[1], 1700.0)

    board = {e.player.id: e.versus_crowd for e in _board(db, user).entries}

    assert board[pool[0].id] == 1  # you have him a place higher
    assert board[pool[1].id] == -1


def test_agreeing_with_the_crowd_reads_as_no_movement(db, pool):
    user = _user(db)
    for i, player in enumerate(pool[:4]):
        _rate(db, user, player, votes=5, rating=1600.0 - i * 10)
        _crowd(db, player, 1900.0 - i * 10)

    assert {e.versus_crowd for e in _board(db, user).entries} == {0}


def test_someone_missing_from_your_board_does_not_move_it(db, pool):
    """The gap has to be disagreement, not a difference in who each list holds.

    Read the crowd's positions off the crowd's own board and a player they rank
    but you have never been dealt takes a slot on it, pushing everyone below him
    down a place — movement nobody voted for. Ranking the crowd over your own
    players is what keeps that out.
    """
    user = _user(db)
    for i, player in enumerate(pool[:4]):
        _rate(db, user, player, votes=5, rating=1600.0 - i * 10)
        _crowd(db, player, 1900.0 - i * 10, votes=9)

    # Second on the crowd's board and entirely absent from yours.
    _crowd(db, pool[4], 1895.0, votes=9)

    board = {e.player.id: e.versus_crowd for e in _board(db, user).entries}

    assert set(board) == {p.id for p in pool[:4]}
    assert all(gap == 0 for gap in board.values()), board


def test_disagreement_about_one_player_moves_the_players_he_passes(db, pool):
    """Not an artefact: rating him over them is exactly what you said."""
    user = _user(db)
    for i, player in enumerate(pool[:3]):
        _rate(db, user, player, votes=5, rating=1600.0 - i * 10)
        _crowd(db, player, 1900.0 - i * 10, votes=9)

    # You have him second; the crowd has him last.
    _rate(db, user, pool[3], votes=5, rating=1595.0)
    _crowd(db, pool[3], 1500.0, votes=9)

    board = {e.player.id: e.versus_crowd for e in _board(db, user).entries}

    assert board[pool[3].id] == 2  # two places higher than the crowd has him
    assert board[pool[1].id] == -1  # because he was passed
    assert board[pool[0].id] == 0


def test_a_player_the_crowd_cannot_place_reports_no_gap(db, pool):
    user = _user(db)
    _rate(db, user, pool[0], votes=5, rating=1600.0)
    _rate(db, user, pool[1], votes=5, rating=1590.0)
    _crowd(db, pool[1], 1700.0)
    # No global rating row at all for pool[0] — nothing to compare him against.
    db.delete(db.get(PlayerRating, pool[0].id))
    db.commit()

    board = {e.player.id: e.versus_crowd for e in _board(db, user).entries}

    assert board[pool[0].id] is None
    assert board[pool[1].id] is not None


def test_the_crowds_own_board_reports_no_gap(db, pool):
    db.get(PlayerRating, pool[0].id).votes = 9
    db.commit()

    board = rankings(league="nfl", position=None, limit=50, offset=0, min_votes=5, db=db)

    assert [e.versus_crowd for e in board.entries] == [None]


def test_the_global_board_keeps_its_own_higher_floor(db, pool):
    """The crowd's board is fed by everyone, so it can afford to ask for more."""
    db.get(PlayerRating, pool[0].id).votes = MIN_VOTES_PERSONAL
    db.commit()

    board = rankings(league="nfl", position=None, limit=50, offset=0, min_votes=5, db=db)

    assert board.total == 0
