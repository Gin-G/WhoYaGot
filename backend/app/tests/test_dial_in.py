"""Dialling in a stretch of a board: settle 20-40 by dealing from 10-50."""

import uuid

import pytest

from database.models import Matchup, User, UserPlayerRating, Vote
from services import matchmaking


@pytest.fixture()
def voter(db):
    user = User(google_sub="dialler")
    db.add(user)
    db.flush()
    return user


def _board(db, user, players):
    """Give the voter a ranked board, best first, all clearly ranked."""
    for place, player in enumerate(players):
        db.add(
            UserPlayerRating(
                user_id=user.id,
                player_id=player.id,
                league="nfl",
                position=player.position,
                rating=2000.0 - place,
                votes=5,
            )
        )
    db.commit()


# --- the window itself --------------------------------------------------------


def test_dialling_twenty_to_forty_deals_from_ten_to_fifty():
    """The example this was asked for."""
    order = list(range(1, 101))
    window = matchmaking.dial_window(order, 20, 40)
    assert window[0] == 10
    assert window[-1] == 50


def test_the_range_asked_for_is_always_inside_the_window():
    order = list(range(1, 201))
    for first, last in [(1, 12), (25, 25), (60, 90), (150, 200)]:
        window = matchmaking.dial_window(order, first, last)
        assert set(range(first, last + 1)) <= set(window), (first, last)


def test_a_window_reaches_past_both_ends():
    """A range cannot be settled against itself."""
    order = list(range(1, 101))
    window = matchmaking.dial_window(order, 40, 60)
    assert min(window) < 40 and max(window) > 60


def test_a_narrow_ask_still_gets_somewhere_to_look():
    order = list(range(1, 101))
    assert len(matchmaking.dial_window(order, 50, 50)) > 1


def test_the_window_stops_at_the_ends_of_the_board():
    order = list(range(1, 21))
    assert matchmaking.dial_window(order, 1, 3)[0] == 1
    assert matchmaking.dial_window(order, 18, 20)[-1] == 20


def test_the_ends_can_be_given_the_wrong_way_round():
    order = list(range(1, 101))
    assert matchmaking.dial_window(order, 40, 20) == matchmaking.dial_window(order, 20, 40)


# --- what gets dealt ----------------------------------------------------------


def test_every_pair_dealt_comes_from_inside_the_window(db, make_pool, voter):
    players = make_pool(60)
    _board(db, voter, players)
    expected = set(matchmaking.dial_window([p.id for p in players], 20, 40))

    for _ in range(25):
        _, a, b = matchmaking.create_matchup(db, "nfl", user_id=voter.id, dial=(20, 40))
        db.commit()
        assert a.id in expected, a.name
        assert b.id in expected, b.name


def test_nobody_outside_the_window_is_ever_dealt(db, make_pool, voter):
    """The top of the board must stay out of a draw aimed at the middle."""
    players = make_pool(60)
    _board(db, voter, players)
    top_five = {p.id for p in players[:5]}

    seen = set()
    for _ in range(25):
        _, a, b = matchmaking.create_matchup(db, "nfl", user_id=voter.id, dial=(30, 40))
        db.commit()
        seen |= {a.id, b.id}
    assert not (seen & top_five)


def test_a_dial_past_the_end_of_a_short_board_is_refused(db, make_pool, voter):
    players = make_pool(6)
    _board(db, voter, players)
    with pytest.raises(matchmaking.NoMatchupAvailable):
        matchmaking.create_matchup(db, "nfl", user_id=voter.id, dial=(400, 420))


def test_without_a_dial_the_ordinary_draw_is_unchanged(db, make_pool, voter):
    players = make_pool(40)
    _board(db, voter, players)
    seen = set()
    for _ in range(30):
        # Pinned, because this pool is quarterbacks only and a crossing draw
        # would have nowhere to cross to.
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB", user_id=voter.id)
        db.commit()
        seen |= {a.id, b.id}
    # A draw over the whole pool reaches wider than any window would.
    assert len(seen) > len(matchmaking.dial_window([p.id for p in players], 20, 30))


def test_the_order_dialled_against_is_the_voters_own(db, make_pool, voter):
    """"Picks 20-40" means theirs, not the crowd's."""
    players = make_pool(30)
    # Their board runs opposite to the global one.
    _board(db, voter, list(reversed(players)))
    order = matchmaking.ranked_order(db, "nfl", voter.id, None)
    assert order[0] == players[-1].id


def test_a_voter_with_no_board_falls_back_to_the_crowd(db, make_pool):
    players = make_pool(10)
    order = matchmaking.ranked_order(db, "nfl", None, None)
    assert len(order) == len(players)


def test_a_board_with_no_picks_still_deals_neighbours(db, make_pool, voter):
    """Top of the window against the bottom is the one pair nobody needs."""
    players = make_pool(60)
    _board(db, voter, players)
    place = {p.id: i for i, p in enumerate(players)}

    for _ in range(30):
        _, a, b = matchmaking.create_matchup(db, "nfl", user_id=voter.id, dial=(20, 40))
        db.commit()
        apart = abs(place[a.id] - place[b.id])
        assert apart <= matchmaking.RANKED_PAIR_SPAN, f"{a.name} vs {b.name}, {apart} apart"
