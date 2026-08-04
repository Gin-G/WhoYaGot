import pytest

from database.models import Player, PlayerRating, Vote
from services import matchmaking


def test_pairs_two_distinct_players_at_the_same_position(db, pool):
    matchup, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
    db.commit()

    assert a.id != b.id
    assert a.position == b.position == "QB"
    assert matchup.player_a_id in {a.id, b.id}


def test_refuses_a_position_the_league_does_not_vote_on(db, pool):
    with pytest.raises(ValueError, match="not a votable position"):
        matchmaking.create_matchup(db, "nfl", position="LS")


def test_reports_an_empty_pool_rather_than_dealing_nothing(db):
    with pytest.raises(matchmaking.NoMatchupAvailable, match="run the player sync"):
        matchmaking.create_matchup(db, "nfl", position="QB")


def test_inactive_players_stay_out_of_the_pool(db, pool):
    for player in pool[2:]:
        player.active = False
    db.commit()

    for _ in range(20):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        assert {a.id, b.id} == {pool[0].id, pool[1].id}
    db.commit()


def test_prefers_opponents_with_a_similar_rating(db, pool):
    # One cluster near 1500, one far above it.
    for player in pool[:4]:
        db.get(PlayerRating, player.id).rating = 1500.0
    for player in pool[4:]:
        db.get(PlayerRating, player.id).rating = 2400.0
    db.commit()

    low = {p.id for p in pool[:4]}
    crossings = 0
    for _ in range(60):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        if (a.id in low) != (b.id in low):
            crossings += 1
    db.commit()

    # The windows widen when nothing closer exists, so a few crossings are
    # expected — but they should be the exception.
    assert crossings < 12


def test_avoids_repeating_a_pair_the_voter_already_judged(db, make_pool):
    make_pool(24)
    session_id = "voter-1"
    seen: set[frozenset[int]] = set()

    # 24 players make 276 distinct pairs, so 40 draws have plenty of room and a
    # repeat would mean the exclusion is not being applied.
    for _ in range(40):
        matchup, a, b = matchmaking.create_matchup(
            db, "nfl", position="QB", session_id=session_id
        )
        pair = frozenset({a.id, b.id})
        assert pair not in seen
        seen.add(pair)

        db.add(
            Vote(
                matchup_id=matchup.id,
                league="nfl",
                position="QB",
                winner_id=a.id,
                loser_id=b.id,
                session_id=session_id,
            )
        )
        db.commit()


def test_one_voters_history_does_not_constrain_another(db, pool):
    matchup, a, b = matchmaking.create_matchup(db, "nfl", position="QB", session_id="v1")
    db.add(
        Vote(
            matchup_id=matchup.id,
            league="nfl",
            position="QB",
            winner_id=a.id,
            loser_id=b.id,
            session_id="v1",
        )
    )
    db.commit()

    excluded = matchmaking._seen_opponents(db, a.id, None, "v2")
    assert excluded == set()


def test_spreads_votes_across_the_pool(db, pool):
    """The coverage bias should stop a few players hogging every matchup."""
    appearances = {p.id: 0 for p in pool}

    for _ in range(200):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        for player in (a, b):
            appearances[player.id] += 1
            rating = db.get(PlayerRating, player.id)
            rating.votes += 1
    db.commit()

    assert min(appearances.values()) > 0
    # No player should appear more than three times as often as the rarest.
    assert max(appearances.values()) / min(appearances.values()) < 3.0


def test_sides_are_randomised(db, pool):
    left = set()
    for _ in range(40):
        matchup, _, _ = matchmaking.create_matchup(db, "nfl", position="QB")
        left.add(matchup.player_a_id)
    db.commit()

    assert len(left) > 2


def test_position_is_chosen_when_the_caller_omits_one(db, pool):
    assert matchmaking.choose_position("nfl", None) in {"QB", "RB", "WR", "TE"}
    assert matchmaking.choose_position("nfl", "qb") == "QB"


def test_players_from_another_league_never_appear(db, pool):
    db.add(
        Player(
            league="mlb",
            external_id="mlb-1",
            name="Wrong Sport",
            position="QB",
            active=True,
        )
    )
    db.commit()

    for _ in range(20):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        assert a.league == b.league == "nfl"
    db.commit()
