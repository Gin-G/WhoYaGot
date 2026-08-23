"""When a place on a personal board stops being an estimate."""

import uuid

import pytest

from database.models import Matchup, User, Vote
from services.settling import analyse, order_by_picks


@pytest.fixture()
def voter(db):
    user = User(google_sub="settled-sub", email="settled@example.com")
    db.add(user)
    db.flush()
    return user


def _pick(db, voter, winner, loser):
    """Record `winner` taken over `loser`, the way a vote arrives."""
    matchup_id = uuid.uuid4().hex
    db.add(
        Matchup(
            id=matchup_id,
            league="nfl",
            player_a_id=winner.id,
            player_b_id=loser.id,
            user_id=voter.id,
            answered=True,
        )
    )
    db.add(
        Vote(
            matchup_id=matchup_id,
            league="nfl",
            winner_id=winner.id,
            loser_id=loser.id,
            user_id=voter.id,
        )
    )
    db.commit()


def _read(db, voter, board):
    """The voter's picks, read against this board — as the endpoint does it."""
    picks = (
        db.query(Vote.winner_id, Vote.loser_id)
        .filter(Vote.user_id == voter.id, Vote.league == "nfl")
        .all()
    )
    return analyse([p.id for p in board], picks)


def _settled(db, voter, board):
    return _read(db, voter, board).settled


def test_nothing_is_settled_without_picks(db, voter, make_pool):
    board = make_pool(4)
    assert _settled(db, voter, board) == set()


def test_the_top_of_the_board_needs_only_the_man_below_him(db, voter, make_pool):
    """Bijan over Gibbs, and first place is a result rather than a rating."""
    board = make_pool(4)
    _pick(db, voter, board[0], board[1])

    settled = _settled(db, voter, board)
    assert board[0].id in settled
    # Second place still has nothing holding it up from underneath.
    assert board[1].id not in settled


def test_a_place_needs_the_men_on_both_sides_of_it(db, voter, make_pool):
    board = make_pool(4)
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])

    settled = _settled(db, voter, board)
    assert board[0].id in settled
    assert board[1].id in settled  # under the first, over the third
    assert board[2].id not in settled  # nothing under him yet


def test_the_foot_of_the_board_needs_only_the_man_above_him(db, voter, make_pool):
    board = make_pool(3)
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])

    assert _settled(db, voter, board) == {p.id for p in board}


def test_a_pick_chains_without_the_pair_ever_meeting(db, voter, make_pool):
    """Beating the man who beat him settles the same order a direct pick would."""
    board = make_pool(3)
    _pick(db, voter, board[0], board[2])  # first over third, skipping second
    _pick(db, voter, board[2], board[1])

    # The board orders 0, 1, 2 by rating, but the picks say 0 > 2 > 1. First
    # place still holds: 0 reaches 1 through 2.
    assert board[0].id in _settled(db, voter, board)


def test_beating_someone_far_below_says_nothing_about_the_next_man(db, voter, make_pool):
    board = make_pool(4)
    _pick(db, voter, board[0], board[3])  # first over fourth only

    # Nothing separates first from second, which is the place in question.
    assert board[0].id not in _settled(db, voter, board)


def test_contradicting_yourself_settles_nothing(db, voter, make_pool):
    """A over B, B over C, C over A: a cycle is not an order."""
    board = make_pool(4)
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])
    _pick(db, voter, board[2], board[0])

    settled = _settled(db, voter, board)
    for player in board[:3]:
        assert player.id not in settled


def test_taking_the_same_pair_both_ways_reopens_them(db, voter, make_pool):
    board = make_pool(3)
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])
    assert board[0].id in _settled(db, voter, board)

    # Changing your mind without taking the first pick back leaves both on
    # record, and a pair pointing at each other is a cycle like any other.
    _pick(db, voter, board[1], board[0])
    assert board[0].id not in _settled(db, voter, board)


def test_another_voters_picks_do_not_settle_your_board(db, voter, make_pool):
    board = make_pool(3)
    stranger = User(google_sub="stranger-sub")
    db.add(stranger)
    db.flush()
    _pick(db, stranger, board[0], board[1])
    _pick(db, stranger, board[1], board[2])

    assert _settled(db, voter, board) == set()


def test_a_board_of_one_has_no_neighbours_to_settle_against(db, voter, make_pool):
    board = make_pool(1)
    assert _settled(db, voter, board) == set()


def test_picks_on_players_off_the_board_are_ignored(db, voter, make_pool):
    """A player below the vote threshold is not a rung anyone can stand on."""
    pool = make_pool(4)
    board = pool[:2]  # the last two never made the board
    _pick(db, voter, pool[0], pool[3])
    _pick(db, voter, pool[3], pool[1])

    # 0 > 3 > 1 chains through a player the board does not carry, so as far as
    # this board is concerned first and second have never been compared.
    assert _settled(db, voter, board) == set()


def test_a_long_chain_settles_every_place_along_it(db, voter, make_pool):
    board = make_pool(30)
    for upper, lower in zip(board, board[1:]):
        _pick(db, voter, upper, lower)

    assert _settled(db, voter, board) == {p.id for p in board}


def test_a_gap_bordering_a_settled_run_is_worth_more_than_one_in_the_open(db, voter, make_pool):
    """`gain` is what makes a board settle outward from what is already done."""
    board = make_pool(6)
    # 0>1>2 settles the top; the rest of the board is untouched.
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])

    reading = _read(db, voter, board)
    last = len(board) - 2
    # Boundary 2 sits against the settled run: closing it settles third place.
    # Boundary 3 has open country on both sides and settles nothing on its own.
    assert reading.gain(2, last) == 1
    assert reading.gain(3, last) == 0
    # The foot of the board counts as a settled edge, since nothing sits under
    # it — so the last boundary is worth a place too.
    assert reading.gain(last, last) == 1


def test_a_cycle_is_not_offered_as_a_gap_to_close(db, voter, make_pool):
    """Another vote cannot break it — the contradicting pick stays on record."""
    board = make_pool(4)
    _pick(db, voter, board[0], board[1])
    _pick(db, voter, board[1], board[2])
    _pick(db, voter, board[2], board[0])

    reading = _read(db, voter, board)
    assert reading.settled == set()
    # Only the gap below the cycle is worth dealing.
    assert reading.open_boundaries == [2]


def test_every_gap_closed_leaves_nothing_to_deal(db, voter, make_pool):
    board = make_pool(5)
    for upper, lower in zip(board, board[1:]):
        _pick(db, voter, upper, lower)

    reading = _read(db, voter, board)
    assert reading.settled == {p.id for p in board}
    assert reading.open_boundaries == []


# --- the order a board is shown in -------------------------------------------


def _order(db, voter, board, strength):
    picks = (
        db.query(Vote.winner_id, Vote.loser_id)
        .filter(Vote.user_id == voter.id, Vote.league == "nfl")
        .all()
    )
    return order_by_picks([p.id for p in board], strength, picks)


def test_a_player_is_never_shown_below_one_he_was_taken_over(db, voter, make_pool):
    """The bug this fixes: three picks beaten by a rating built elsewhere.

    Allen is taken over Maye three times. Maye then beats other people and his
    rating climbs past Allen's, and the board used to answer the one question
    the voter actually asked about the pair with the opposite of their answer.
    """
    board = make_pool(5)
    allen, maye = board[4], board[0]
    strength = {p.id: r for p, r in zip(board, [1560.0, 1520.0, 1510.0, 1505.0, 1450.0])}

    for _ in range(3):
        _pick(db, voter, allen, maye)
    _pick(db, voter, maye, board[1])

    order = _order(db, voter, board, strength)
    assert order.index(allen.id) < order.index(maye.id)


def test_the_rating_still_orders_everyone_the_picks_are_silent_about(db, voter, make_pool):
    board = make_pool(4)
    strength = {p.id: r for p, r in zip(board, [1600.0, 1500.0, 1400.0, 1300.0])}
    assert _order(db, voter, board, strength) == [p.id for p in board]


def test_a_pick_lifts_a_player_without_dragging_the_board_with_him(db, voter, make_pool):
    """Only the order the pick actually decides changes; the rest holds."""
    board = make_pool(5)
    low, high = board[4], board[0]
    strength = {p.id: r for p, r in zip(board, [1600.0, 1550.0, 1500.0, 1450.0, 1400.0])}
    _pick(db, voter, low, high)

    order = _order(db, voter, board, strength)
    # He comes out directly above the man he beat, not parked at the top by
    # rating, and everyone the pick says nothing about keeps their order.
    assert order[0] == low.id
    assert order[1] == high.id
    assert order[2:] == [board[1].id, board[2].id, board[3].id]


def test_the_balance_of_repeated_picks_decides_the_pair(db, voter, make_pool):
    board = make_pool(2)
    upper, lower = board
    strength = {upper.id: 1600.0, lower.id: 1400.0}

    for _ in range(3):
        _pick(db, voter, lower, upper)
    _pick(db, voter, upper, lower)  # one the other way: 3-1, still his

    assert _order(db, voter, board, strength)[0] == lower.id


def test_a_pair_level_on_picks_falls_back_to_the_rating(db, voter, make_pool):
    board = make_pool(2)
    upper, lower = board
    strength = {upper.id: 1600.0, lower.id: 1400.0}
    _pick(db, voter, lower, upper)
    _pick(db, voter, upper, lower)

    assert _order(db, voter, board, strength) == [upper.id, lower.id]


def test_a_knot_of_contradictions_keeps_its_place_and_sorts_by_rating(db, voter, make_pool):
    board = make_pool(5)
    strength = {p.id: r for p, r in zip(board, [1600.0, 1550.0, 1500.0, 1450.0, 1400.0])}
    _pick(db, voter, board[1], board[2])
    _pick(db, voter, board[2], board[3])
    _pick(db, voter, board[3], board[1])

    order = _order(db, voter, board, strength)
    assert order[0] == board[0].id  # untouched by the knot
    assert order[1:4] == [board[1].id, board[2].id, board[3].id]
    assert order[4] == board[4].id


def test_ordering_by_picks_makes_a_chain_settle_end_to_end(db, voter, make_pool):
    """The two halves agree: order by the picks and the picks settle the order."""
    board = make_pool(6)
    # Deliberately backwards against the rating, all the way down.
    strength = {p.id: 1400.0 + i * 20 for i, p in enumerate(board)}
    for upper, lower in zip(board, board[1:]):
        _pick(db, voter, upper, lower)

    order = _order(db, voter, board, strength)
    assert order == [p.id for p in board]
    picks = (
        db.query(Vote.winner_id, Vote.loser_id)
        .filter(Vote.user_id == voter.id, Vote.league == "nfl")
        .all()
    )
    assert analyse(order, picks).settled == {p.id for p in board}


def test_a_chain_does_not_run_through_a_contradiction(db, voter, make_pool):
    """Beating a player caught in a knot says nothing about who is behind him.

    Everyone inside a contradiction reaches everyone else there, so a chain let
    through one would come out the far side proving whatever it liked.
    """
    board = make_pool(5)
    top, a, b, c, bottom = board
    # Top beats one member of the knot, and the board happens to sit a
    # different member directly beneath him.
    _pick(db, voter, top, c)
    _pick(db, voter, a, b)
    _pick(db, voter, b, c)
    _pick(db, voter, c, a)
    _pick(db, voter, a, bottom)

    reading = _read(db, voter, board)
    # He has shown himself over one of them, not over the man actually below
    # him — and the only route there runs through the contradiction, where the
    # picks point both ways at once.
    assert top.id not in reading.settled
    assert bottom.id not in reading.settled
