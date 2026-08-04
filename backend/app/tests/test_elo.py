from database.models import PlayerRating, UserPlayerRating
from services import elo


def test_even_matchup_moves_both_by_the_same_amount(db, pool):
    winner, loser = pool[0], pool[1]
    result = elo.record_result(db, winner, loser)
    db.commit()

    assert result["global"]["winner"]["delta"] == 20.0
    assert result["global"]["loser"]["delta"] == -20.0
    assert db.get(PlayerRating, winner.id).rating == 1520.0
    assert db.get(PlayerRating, loser.id).rating == 1480.0


def test_beating_a_weaker_player_earns_less(db, pool):
    strong, weak = pool[0], pool[1]
    db.get(PlayerRating, strong.id).rating = 1900.0
    db.get(PlayerRating, weak.id).rating = 1100.0
    db.commit()

    expected_gain = elo.record_result(db, strong, weak)["global"]["winner"]["delta"]
    assert 0 < expected_gain < 2.0


def test_upset_swings_hard(db, pool):
    strong, weak = pool[0], pool[1]
    db.get(PlayerRating, strong.id).rating = 1900.0
    db.get(PlayerRating, weak.id).rating = 1100.0
    db.commit()

    upset = elo.record_result(db, weak, strong)["global"]["winner"]["delta"]
    assert upset > 38.0


def test_k_factor_falls_as_votes_accumulate():
    assert elo.k_factor(0) > elo.k_factor(50) > elo.k_factor(500)


def test_anonymous_vote_touches_only_the_global_ladder(db, pool):
    result = elo.record_result(db, pool[0], pool[1], user_id=None)
    db.commit()

    assert "personal" not in result
    assert db.query(UserPlayerRating).count() == 0


def test_signed_in_vote_updates_both_ladders(db, pool):
    result = elo.record_result(db, pool[0], pool[1], user_id=7)
    db.commit()

    assert result["personal"]["winner"]["delta"] == 20.0
    assert db.get(UserPlayerRating, (7, pool[0].id)).rating == 1520.0
    # One user's opinion must not be visible in anyone else's list.
    assert db.get(UserPlayerRating, (9, pool[0].id)) is None


def test_expected_score_is_symmetric():
    assert elo.expected_score(1500, 1500) == 0.5
    assert elo.expected_score(1700, 1500) + elo.expected_score(1500, 1700) == 1.0
