"""Taking a pick back, and changing your mind about one."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from api.picks import my_picks, revise_pick, undo_pick
from database.models import Matchup, PlayerRating, User, UserPlayerRating, Vote
from schemas import RevisePickIn
from services import elo


def _vote(db, winner, loser, *, user_id=None, session_id=None, at=None, position="QB"):
    matchup_id = uuid.uuid4().hex
    db.add(
        Matchup(
            id=matchup_id,
            league="nfl",
            position=position,
            player_a_id=winner.id,
            player_b_id=loser.id,
            user_id=user_id,
            session_id=session_id,
            answered=True,
        )
    )
    vote = Vote(
        matchup_id=matchup_id,
        league="nfl",
        position=position,
        winner_id=winner.id,
        loser_id=loser.id,
        user_id=user_id,
        session_id=session_id,
        created_at=at or datetime.now(timezone.utc),
    )
    db.add(vote)
    elo.record_result(db, winner, loser, user_id=user_id)
    db.commit()
    return vote


@pytest.fixture()
def voter(db):
    user = User(google_sub="sub-1")
    db.add(user)
    db.commit()
    return user


def _picks(db, user=None, session_id=None, **kwargs):
    params = {
        "league": "nfl",
        "position": None,
        "player_id": None,
        "limit": 50,
        "offset": 0,
        "db": db,
        "user": user,
        "session_id": session_id,
    }
    return my_picks(**{**params, **kwargs})


def _rating(db, user_id, player):
    return db.get(UserPlayerRating, (user_id, player.id))


# --- Reading them back ------------------------------------------------------


def test_picks_come_back_newest_first(db, pool, voter):
    now = datetime.now(timezone.utc)
    _vote(db, pool[0], pool[1], user_id=voter.id, at=now - timedelta(minutes=5))
    _vote(db, pool[2], pool[3], user_id=voter.id, at=now)

    picks = _picks(db, user=voter)

    assert picks.total == 2
    assert [p.winner.id for p in picks.picks] == [pool[2].id, pool[0].id]


def test_one_players_picks_can_be_pulled_out(db, pool, voter):
    """The question you ask when someone looks misplaced: who did I face him with?"""
    tate = pool[0]
    _vote(db, tate, pool[1], user_id=voter.id)
    _vote(db, pool[2], tate, user_id=voter.id)
    _vote(db, pool[3], pool[4], user_id=voter.id)

    picks = _picks(db, user=voter, player_id=tate.id)

    assert picks.total == 2
    # Both sides of him: the one he won and the one he lost.
    assert {p.winner.id for p in picks.picks} == {tate.id, pool[2].id}


def test_a_voter_only_sees_their_own_picks(db, pool, voter):
    _vote(db, pool[0], pool[1], user_id=voter.id)
    _vote(db, pool[2], pool[3], session_id="someone-else")

    assert _picks(db, user=voter).total == 1
    assert _picks(db, session_id="someone-else").total == 1
    assert _picks(db, session_id="a-third-party").total == 0


def test_an_unidentified_caller_gets_nothing_rather_than_everything(db, pool, voter):
    _vote(db, pool[0], pool[1], user_id=voter.id)

    assert _picks(db).total == 0


# --- Taking one back --------------------------------------------------------


def test_undoing_a_pick_leaves_the_ladder_as_if_it_never_happened(db, pool, voter):
    before = _vote(db, pool[0], pool[1], user_id=voter.id)
    settled = _rating(db, voter.id, pool[0]).rating

    mistake = _vote(db, pool[2], pool[3], user_id=voter.id)
    undo_pick(mistake.id, db=db, user=voter, session_id=None)

    assert db.query(Vote).count() == 1
    assert db.get(Vote, before.id) is not None
    assert _rating(db, voter.id, pool[0]).rating == pytest.approx(settled)
    # The player who wrongly won is back where he started.
    assert _rating(db, voter.id, pool[2]) is None


def test_undoing_an_early_pick_reprices_everything_after_it(db, pool, voter):
    """Elo is path-dependent, so this cannot be a subtraction."""
    first = _vote(db, pool[0], pool[1], user_id=voter.id)
    for winner, loser in ((pool[0], pool[2]), (pool[0], pool[3]), (pool[1], pool[4])):
        _vote(db, winner, loser, user_id=voter.id)
    with_first = _rating(db, voter.id, pool[0]).rating

    undo_pick(first.id, db=db, user=voter, session_id=None)

    after = _rating(db, voter.id, pool[0])
    assert after.wins == 2 and after.losses == 0
    # Beating pool[1] raised his rating, which made the later wins worth less;
    # removing it has to change what those later wins were worth.
    assert after.rating != pytest.approx(with_first)


def test_an_undone_pair_can_be_dealt_again(db, pool, voter):
    vote = _vote(db, pool[0], pool[1], user_id=voter.id)
    matchup_id = vote.matchup_id

    undo_pick(vote.id, db=db, user=voter, session_id=None)

    assert db.get(Matchup, matchup_id).answered is False


def test_you_cannot_undo_someone_elses_pick(db, pool, voter):
    theirs = _vote(db, pool[0], pool[1], session_id="not-you")

    with pytest.raises(HTTPException) as exc:
        undo_pick(theirs.id, db=db, user=voter, session_id=None)

    assert exc.value.status_code == 404
    assert db.query(Vote).count() == 1


def test_undoing_a_pick_that_does_not_exist_says_so(db, pool, voter):
    with pytest.raises(HTTPException) as exc:
        undo_pick(9999, db=db, user=voter, session_id=None)

    assert exc.value.status_code == 404


def test_an_anonymous_voter_can_undo_their_own(db, pool):
    vote = _vote(db, pool[0], pool[1], session_id="anon-1")

    undo_pick(vote.id, db=db, user=None, session_id="anon-1")

    assert db.query(Vote).count() == 0


# --- Changing your mind -----------------------------------------------------


def test_revising_a_pick_swaps_who_won(db, pool, voter):
    """Took Tate over St. Brown too quickly."""
    vote = _vote(db, pool[0], pool[1], user_id=voter.id)

    revise_pick(vote.id, RevisePickIn(winner_id=pool[1].id), db=db, user=voter, session_id=None)

    revised = db.get(Vote, vote.id)
    assert revised.winner_id == pool[1].id
    assert revised.loser_id == pool[0].id
    assert _rating(db, voter.id, pool[1]).wins == 1
    assert _rating(db, voter.id, pool[0]).losses == 1


def test_revising_puts_the_two_ladders_where_a_correct_pick_would_have(db, pool, voter):
    wrong = _vote(db, pool[0], pool[1], user_id=voter.id)
    _vote(db, pool[2], pool[3], user_id=voter.id)
    revise_pick(wrong.id, RevisePickIn(winner_id=pool[1].id), db=db, user=voter, session_id=None)
    revised = {p.id: _rating(db, voter.id, p).rating for p in pool[:4]}
    globals_after = {p.id: db.get(PlayerRating, p.id).rating for p in pool[:4]}

    # Now build the same history from scratch with the pick made correctly.
    for table in (Vote, UserPlayerRating):
        db.query(table).delete()
    db.query(PlayerRating).update({"rating": 1500.0, "wins": 0, "losses": 0, "votes": 0})
    db.commit()
    _vote(db, pool[1], pool[0], user_id=voter.id)
    _vote(db, pool[2], pool[3], user_id=voter.id)

    assert {p.id: _rating(db, voter.id, p).rating for p in pool[:4]} == pytest.approx(revised)
    assert {p.id: db.get(PlayerRating, p.id).rating for p in pool[:4]} == pytest.approx(
        globals_after
    )


def test_revising_to_the_same_winner_changes_nothing(db, pool, voter):
    vote = _vote(db, pool[0], pool[1], user_id=voter.id)
    before = _rating(db, voter.id, pool[0]).rating

    revise_pick(vote.id, RevisePickIn(winner_id=pool[0].id), db=db, user=voter, session_id=None)

    assert _rating(db, voter.id, pool[0]).rating == pytest.approx(before)


def test_a_player_who_was_not_in_the_pick_cannot_win_it(db, pool, voter):
    vote = _vote(db, pool[0], pool[1], user_id=voter.id)

    with pytest.raises(HTTPException) as exc:
        revise_pick(
            vote.id, RevisePickIn(winner_id=pool[5].id), db=db, user=voter, session_id=None
        )

    assert exc.value.status_code == 400


def test_you_cannot_revise_someone_elses_pick(db, pool, voter):
    theirs = _vote(db, pool[0], pool[1], session_id="not-you")

    with pytest.raises(HTTPException) as exc:
        revise_pick(
            theirs.id, RevisePickIn(winner_id=pool[1].id), db=db, user=voter, session_id=None
        )

    assert exc.value.status_code == 404


# --- starting a player over ---------------------------------------------------


def test_resetting_a_player_takes_back_every_pick_he_was_in(db, make_pool):
    """The preseason case: what was answered about him is no longer the question."""
    players = make_pool(6)
    injured, others = players[0], players[1:]
    user = User(google_sub="reset-1")
    db.add(user)
    db.flush()

    for other in others:
        _vote(db, injured, other, user_id=user.id)
    # A pick with nothing to do with him, which must survive untouched.
    _vote(db, others[0], others[1], user_id=user.id)
    db.commit()

    from api.picks import reset_player

    out = reset_player(injured.id, league="nfl", db=db, user=user, session_id=None)

    survivors = db.query(Vote).filter(Vote.user_id == user.id).all()
    assert len(survivors) == 1
    assert injured.id not in (survivors[0].winner_id, survivors[0].loser_id)
    assert out.total == 1


def test_a_reset_player_falls_off_the_board(db, make_pool):
    players = make_pool(6)
    injured, others = players[0], players[1:]
    user = User(google_sub="reset-2")
    db.add(user)
    db.flush()
    for other in others:
        _vote(db, injured, other, user_id=user.id)
    db.commit()

    before = db.get(UserPlayerRating, (user.id, injured.id))
    assert before is not None and before.votes >= 3

    from api.picks import reset_player

    reset_player(injured.id, league="nfl", db=db, user=user, session_id=None)

    after = db.get(UserPlayerRating, (user.id, injured.id))
    assert after is None or after.votes == 0


def test_resetting_a_player_puts_his_pairs_back_on_the_table(db, make_pool):
    """The answers will be different now, so the questions deserve asking again."""
    players = make_pool(4)
    injured, other = players[0], players[1]
    user = User(google_sub="reset-3")
    db.add(user)
    db.flush()
    vote = _vote(db, injured, other, user_id=user.id)
    matchup_id = vote.matchup_id
    db.commit()
    assert db.get(Matchup, matchup_id).answered is True

    from api.picks import reset_player

    reset_player(injured.id, league="nfl", db=db, user=user, session_id=None)
    assert db.get(Matchup, matchup_id).answered is False


def test_a_reset_leaves_everyone_elses_places_alone(db, make_pool):
    """Removing him removes what he was evidence for, and nothing besides."""
    players = make_pool(6)
    injured = players[0]
    a, b, c = players[1], players[2], players[3]
    user = User(google_sub="reset-4")
    db.add(user)
    db.flush()
    _vote(db, a, b, user_id=user.id)
    _vote(db, b, c, user_id=user.id)
    _vote(db, injured, a, user_id=user.id)
    db.commit()

    from api.picks import reset_player

    reset_player(injured.id, league="nfl", db=db, user=user, session_id=None)

    # a still over b, b still over c, on the ladder rebuilt without him.
    rating = lambda p: db.get(UserPlayerRating, (user.id, p.id)).rating
    assert rating(a) > rating(b) > rating(c)


def test_a_reset_only_touches_the_asker(db, make_pool):
    players = make_pool(4)
    injured, other = players[0], players[1]
    mine = User(google_sub="reset-5")
    theirs = User(google_sub="reset-6")
    db.add_all([mine, theirs])
    db.flush()
    _vote(db, injured, other, user_id=mine.id)
    _vote(db, injured, other, user_id=theirs.id)
    db.commit()

    from api.picks import reset_player

    reset_player(injured.id, league="nfl", db=db, user=mine, session_id=None)

    assert db.query(Vote).filter(Vote.user_id == mine.id).count() == 0
    assert db.query(Vote).filter(Vote.user_id == theirs.id).count() == 1


def test_resetting_a_player_nobody_has_judged_is_harmless(db, make_pool):
    players = make_pool(3)
    user = User(google_sub="reset-7")
    db.add(user)
    db.flush()
    _vote(db, players[1], players[2], user_id=user.id)
    db.commit()

    from api.picks import reset_player

    out = reset_player(players[0].id, league="nfl", db=db, user=user, session_id=None)
    assert out.total == 1


def test_resetting_an_unknown_player_is_refused(db, make_pool):
    make_pool(3)
    user = User(google_sub="reset-8")
    db.add(user)
    db.flush()
    db.commit()

    from api.picks import reset_player

    with pytest.raises(HTTPException) as raised:
        reset_player(999999, league="nfl", db=db, user=user, session_id=None)
    assert raised.value.status_code == 404
