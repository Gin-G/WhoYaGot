"""When a place on a personal board stops being an estimate."""

import uuid

import pytest

from database.models import Matchup, User, Vote
from services.settling import analyse


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
