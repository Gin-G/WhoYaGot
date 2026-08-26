"""Changing your mind about a pair: the last answer is the only one."""

import uuid

import pytest

from api.matchups import cast_vote
from database.models import Matchup, User, UserPlayerRating, Vote
from schemas import VoteIn
from services.settling import analyse, order_by_picks


@pytest.fixture()
def voter(db):
    user = User(google_sub="mind-changer")
    db.add(user)
    db.flush()
    return user


def _deal(db, a, b, user):
    matchup = Matchup(
        id=uuid.uuid4().hex,
        league="nfl",
        position="QB",
        player_a_id=a.id,
        player_b_id=b.id,
        user_id=user.id,
        answered=False,
    )
    db.add(matchup)
    db.commit()
    return matchup


def _answer(db, matchup, winner, user):
    return cast_vote(
        payload=VoteIn(matchup_id=matchup.id, winner_id=winner.id),
        next_position=None,
        # Called straight rather than through FastAPI, so every parameter it
        # would normally resolve from the query string has to be handed over.
        dial_from=None,
        dial_to=None,
        db=db,
        user=user,
        session_id=None,
    )


def test_the_later_answer_replaces_the_earlier_one(db, make_pool, voter):
    """Coleman over Boutte in August, Boutte over Coleman today."""
    coleman, boutte = make_pool(2)

    _answer(db, _deal(db, coleman, boutte, voter), coleman, voter)
    assert db.query(Vote).count() == 1

    _answer(db, _deal(db, coleman, boutte, voter), boutte, voter)
    votes = db.query(Vote).all()
    assert len(votes) == 1
    assert votes[0].winner_id == boutte.id


def test_the_board_follows_the_change(db, make_pool, voter):
    """Boutte should come out ahead, not tied with himself."""
    coleman, boutte = make_pool(2)
    _answer(db, _deal(db, coleman, boutte, voter), coleman, voter)
    _answer(db, _deal(db, coleman, boutte, voter), boutte, voter)

    picks = db.query(Vote.winner_id, Vote.loser_id).all()
    ratings = {
        r.player_id: r.rating
        for r in db.query(UserPlayerRating).filter(UserPlayerRating.user_id == voter.id)
    }
    order = order_by_picks([coleman.id, boutte.id], ratings, picks)
    assert order[0] == boutte.id


def test_changing_your_mind_settles_rather_than_knots(db, make_pool, voter):
    """Two opposite answers left on record would read as a contradiction.

    The voter is not contradicting themselves — they used to think one thing and
    now think another, which is a settled opinion, not a knot.
    """
    coleman, boutte = make_pool(2)
    _answer(db, _deal(db, coleman, boutte, voter), coleman, voter)
    _answer(db, _deal(db, coleman, boutte, voter), boutte, voter)

    picks = db.query(Vote.winner_id, Vote.loser_id).all()
    reading = analyse([boutte.id, coleman.id], picks)
    assert reading.settled == {boutte.id, coleman.id}
    assert reading.open_boundaries == []


def test_the_ladder_forgets_what_it_was_told_first(db, make_pool, voter):
    """A replaced answer must not still be pushing the man it favoured."""
    coleman, boutte = make_pool(2)
    for _ in range(3):
        _answer(db, _deal(db, coleman, boutte, voter), coleman, voter)
    _answer(db, _deal(db, coleman, boutte, voter), boutte, voter)

    ratings = {
        r.player_id: r.rating
        for r in db.query(UserPlayerRating).filter(UserPlayerRating.user_id == voter.id)
    }
    assert ratings[boutte.id] > ratings[coleman.id]
    # One vote each, not four: the replaced ones are gone from the record.
    counts = {
        r.player_id: r.votes
        for r in db.query(UserPlayerRating).filter(UserPlayerRating.user_id == voter.id)
    }
    assert set(counts.values()) == {1}


def test_a_different_pair_is_left_alone(db, make_pool, voter):
    a, b, c = make_pool(3)
    _answer(db, _deal(db, a, b, voter), a, voter)
    _answer(db, _deal(db, a, c, voter), a, voter)
    assert db.query(Vote).count() == 2


def test_another_voters_answer_on_the_same_pair_survives(db, make_pool, voter):
    a, b = make_pool(2)
    stranger = User(google_sub="stranger")
    db.add(stranger)
    db.flush()

    _answer(db, _deal(db, a, b, stranger), a, stranger)
    _answer(db, _deal(db, a, b, voter), b, voter)

    assert db.query(Vote).filter(Vote.user_id == stranger.id).count() == 1
    assert db.query(Vote).filter(Vote.user_id == voter.id).count() == 1


def test_the_result_reports_the_movement_that_actually_happened(db, make_pool, voter):
    """A rebuild has no delta of its own; the figure has to be measured."""
    a, b = make_pool(2)
    _answer(db, _deal(db, a, b, voter), a, voter)
    out = _answer(db, _deal(db, a, b, voter), b, voter)

    personal = out.ratings["personal"]
    assert personal["winner"]["delta"] > 0
    assert personal["loser"]["delta"] < 0
