import uuid
from itertools import combinations

import pytest

from database.models import Matchup, Player, PlayerRating, Vote
from services import matchmaking


def _record_votes(db, session_id, pairs, position="QB"):
    """Give a voter a history: the first player of each pair beat the second."""
    for winner, loser in pairs:
        matchup_id = uuid.uuid4().hex
        db.add(
            Matchup(
                id=matchup_id,
                league="nfl",
                position=position,
                player_a_id=winner.id,
                player_b_id=loser.id,
                session_id=session_id,
                answered=True,
            )
        )
        db.add(
            Vote(
                matchup_id=matchup_id,
                league="nfl",
                position=position,
                winner_id=winner.id,
                loser_id=loser.id,
                session_id=session_id,
            )
        )
    db.commit()


def test_pairs_two_distinct_players_at_the_same_position(db, pool):
    matchup, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
    db.commit()

    assert a.id != b.id
    assert a.position == b.position == "QB"
    assert matchup.player_a_id in {a.id, b.id}


def _rate_usage(db, players):
    """Score `players` by how much they will be on the field, best first."""
    for i, player in enumerate(players):
        player.usage = 200.0 - i
    db.commit()


def test_only_the_players_who_will_take_the_field_are_dealt(db, make_pool, monkeypatch):
    """A 90-man roster is mostly camp bodies nobody could rank."""
    players = make_pool(40)
    _rate_usage(db, players)
    monkeypatch.setattr(matchmaking.get_source("nfl"), "pool_depth", {"QB": 10})

    for _ in range(60):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        assert a.usage >= 191.0 and b.usage >= 191.0
    db.commit()


def test_the_cut_follows_the_usage_score_not_the_roster_order(db, make_pool, monkeypatch):
    players = make_pool(20)
    # The last three on the roster are the only ones projected to play.
    for player in players:
        player.usage = 1.0
    for player in players[-3:]:
        player.usage = 150.0
    db.commit()
    monkeypatch.setattr(matchmaking.get_source("nfl"), "pool_depth", {"QB": 3})

    dealt = set()
    for _ in range(30):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        dealt |= {a.id, b.id}
    db.commit()

    assert dealt == {p.id for p in players[-3:]}


def test_an_unscored_pool_is_dealt_whole_rather_than_emptied(db, pool, monkeypatch):
    """Nothing scored yet is a reason to keep going, not to stop dealing."""
    monkeypatch.setattr(matchmaking.get_source("nfl"), "pool_depth", {"QB": 4})

    dealt = set()
    for _ in range(40):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        dealt |= {a.id, b.id}
    db.commit()

    assert dealt == {p.id for p in pool}


def test_a_position_with_no_depth_set_keeps_its_whole_roster(db, make_pool, monkeypatch):
    players = make_pool(12)
    _rate_usage(db, players)
    monkeypatch.setattr(matchmaking.get_source("nfl"), "pool_depth", {"WR": 4})

    dealt = set()
    for _ in range(60):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        dealt |= {a.id, b.id}
    db.commit()

    assert dealt == {p.id for p in players}


def test_a_player_below_the_cut_keeps_the_rating_he_earned(db, make_pool, monkeypatch):
    players = make_pool(20)
    _rate_usage(db, players)
    fringe = players[-1]
    db.get(PlayerRating, fringe.id).rating = 1610.0
    db.commit()
    monkeypatch.setattr(matchmaking.get_source("nfl"), "pool_depth", {"QB": 5})

    for _ in range(40):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        assert fringe.id not in {a.id, b.id}
    db.commit()

    assert db.get(PlayerRating, fringe.id).rating == 1610.0


# --- Crossing positions -----------------------------------------------------


@pytest.fixture()
def league_pool(db, make_pool):
    """A pool at every votable position, not just quarterbacks."""
    make_pool(12)
    players = []
    for position in ("RB", "WR", "TE"):
        for i in range(12):
            player = Player(
                league="nfl",
                external_id=f"{position}-{i:04d}",
                name=f"Test {position}{i}",
                position=position,
                team_abbr="BUF",
                active=True,
            )
            db.add(player)
            players.append(player)
    db.flush()
    for player in players:
        db.add(
            PlayerRating(
                player_id=player.id, league="nfl", position=player.position, rating=1500.0
            )
        )
    db.commit()
    return players


def test_an_open_request_crosses_positions(db, league_pool):
    """Gibbs or Chase is the question a single ranking has to answer."""
    crossed = 0
    for _ in range(200):
        _, a, b = matchmaking.create_matchup(db, "nfl")
        if a.position != b.position:
            crossed += 1
    db.commit()

    assert 0.3 < crossed / 200 < 0.7


def test_a_pinned_position_is_never_crossed(db, league_pool):
    for _ in range(80):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB")
        assert a.position == b.position == "QB"
    db.commit()


def test_a_crossed_matchup_belongs_to_no_position(db, league_pool):
    """Storing one of the two would pin the follow-up to it."""
    for _ in range(80):
        matchup, a, b = matchmaking.create_matchup(db, "nfl")
        if a.position != b.position:
            assert matchup.position is None
        else:
            assert matchup.position == a.position
    db.commit()


def test_players_are_crossed_against_their_opposite_number(db, league_pool):
    """The best back against the best receiver, not against the fortieth."""
    by_position = {}
    for player in db.query(Player).filter(Player.active.is_(True)).all():
        by_position.setdefault(player.position, []).append(player)

    # Give every position a clear pecking order on its own scale, and make the
    # scales disagree — TE spread narrowly, QB widely, as an unmerged ladder is.
    spread = {"QB": 90.0, "RB": 70.0, "WR": 70.0, "TE": 20.0}
    place = {}
    for position, players in by_position.items():
        for rank, player in enumerate(sorted(players, key=lambda p: p.id)):
            rating = db.get(PlayerRating, player.id)
            rating.rating = 1500.0 + spread[position] * (6 - rank)
            # Voted in, so the standing follows the rating rather than falling
            # back on what the player was projected to do.
            rating.votes = 20
            place[player.id] = rank
    db.commit()

    gaps = []
    for _ in range(200):
        _, a, b = matchmaking.create_matchup(db, "nfl")
        if a.position != b.position:
            gaps.append(abs(place[a.id] - place[b.id]))
    db.commit()

    assert gaps, "no crossed pairs were dealt"
    # Twelve deep per position, so an unguided draw would average about four
    # places apart. Standing-matched pairs should sit far closer than that.
    assert sum(gaps) / len(gaps) < 2.0


def test_crossing_survives_a_position_whose_ladder_has_barely_moved(db, league_pool):
    """The real case: TE had a fifth of QB's votes, so its whole range was tight."""
    tes = [p for p in db.query(Player).filter(Player.position == "TE").all()]
    best_te = min(tes, key=lambda p: p.id)
    for player in db.query(Player).filter(Player.active.is_(True)).all():
        rating = db.get(PlayerRating, player.id)
        rating.rating = 1500.0 if player.position == "TE" else 1400.0
        rating.votes = 20
    # The best TE is top of his position but numerically below every QB.
    db.get(PlayerRating, best_te.id).rating = 1577.0
    for i, player in enumerate(sorted(
        [p for p in db.query(Player).filter(Player.position == "QB").all()], key=lambda p: p.id
    )):
        db.get(PlayerRating, player.id).rating = 1646.0 - i * 10
    db.commit()

    # Where every player sits in his own position, best first.
    place = {}
    for position in ("QB", "RB", "WR", "TE"):
        group = sorted(
            db.query(Player).filter(Player.position == position).all(), key=lambda p: p.id
        )
        place.update({player.id: rank for rank, player in enumerate(group)})

    faced = []
    for _ in range(300):
        _, a, b = matchmaking.create_matchup(db, "nfl")
        if best_te.id in (a.id, b.id) and a.position != b.position:
            faced.append(b if a.id == best_te.id else a)
    db.commit()

    # Which positions he happens to be drawn against over 300 deals is a coin
    # toss — he comes up in only a handful of crossed pairs. That every one of
    # them is near the top of its own position is the part that must hold.
    assert len(faced) >= 2
    assert all(place[other.id] <= 3 for other in faced), {
        other.name: place[other.id] for other in faced
    }


def _standing_of(db, players):
    pool = [(p, db.get(PlayerRating, p.id)) for p in players]
    return matchmaking._standing(pool)


def test_one_lucky_result_does_not_outrank_a_player_nobody_has_seen(db, make_pool):
    """Tight ends average one vote each; rating alone would be noise there."""
    players = make_pool(6)
    for i, player in enumerate(players):
        player.usage = 200.0 - i * 10  # players[0] is the best projected

    stud, backup = players[0], players[5]
    # The backup won his only matchup; the stud has never been dealt.
    backup_rating = db.get(PlayerRating, backup.id)
    backup_rating.rating, backup_rating.votes = 1540.0, 1
    db.commit()

    standing = _standing_of(db, players)

    assert standing[stud.id] < standing[backup.id]


def test_a_well_voted_rating_outweighs_the_projection(db, make_pool):
    """Once the voter has really spoken, their opinion carries the pecking order.

    It does not quite overturn it: a player nobody has been dealt sits at his
    projection at face value, because that projection is the best thing known
    about him. Discounting the unseen toward the middle would drag every
    unvoted tight end into mid-tier and lose the best-against-best pairing this
    exists to produce.
    """
    players = make_pool(6)
    for i, player in enumerate(players):
        player.usage = 200.0 - i * 10

    # The model's worst is the voter's best, said often enough to mean it.
    riser = players[5]
    rating = db.get(PlayerRating, riser.id)
    rating.rating, rating.votes = 1800.0, 40
    db.commit()

    standing = _standing_of(db, players)
    order = sorted(players, key=lambda p: standing[p.id])

    assert order.index(riser) <= 1  # up from last of six
    assert standing[riser.id] < standing[players[1].id]


def test_an_unvoted_position_is_ordered_by_projection_alone(db, make_pool):
    players = make_pool(5)
    for i, player in enumerate(players):
        player.usage = 100.0 - i
    db.commit()

    standing = _standing_of(db, players)

    # Nothing voted, so the order is exactly the projection's, best to worst.
    assert sorted(players, key=lambda p: standing[p.id]) == players
    assert standing[players[0].id] == 0.0
    assert standing[players[-1].id] == 1.0


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

    history = matchmaking._history(db, "nfl", None, "v2")
    assert matchmaking._seen_opponents(history, a.id) == set()

    history = matchmaking._history(db, "nfl", None, "v1")
    assert matchmaking._seen_opponents(history, a.id) == {b.id}


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


def _both_ranked_share(db, session_id, ranked_ids, deals=400):
    """Share of dealt pairs where the voter had already ranked both players."""
    both = 0
    for _ in range(deals):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB", session_id=session_id)
        if a.id in ranked_ids and b.id in ranked_ids:
            both += 1
    db.commit()
    return both / deals


def test_regularly_pits_two_already_ranked_players_against_each_other(db, make_pool):
    """Otherwise a voter's list is a pile of unbeaten players who never met."""
    players = make_pool(60)
    ranked = players[:12]
    ranked_ids = {p.id for p in ranked}

    # 22 votes among a dozen players — past the threshold, and small enough that
    # the ordinary draw would land on two of them only ~4% of the time.
    pairs = list(combinations(ranked, 2))[::3]
    _record_votes(db, "voter-1", pairs)
    assert len(pairs) >= matchmaking.RANKED_PAIR_MIN_VOTES

    share = _both_ranked_share(db, "voter-1", ranked_ids)
    assert 0.15 < share < 0.45


def test_no_consolidation_before_the_voter_has_a_list_worth_sorting(db, make_pool):
    players = make_pool(60)
    ranked = players[:12]

    pairs = list(combinations(ranked, 2))[::3][: matchmaking.RANKED_PAIR_MIN_VOTES - 1]
    _record_votes(db, "voter-1", pairs)

    share = _both_ranked_share(db, "voter-1", {p.id for p in ranked})
    assert share < 0.10


def test_consolidation_never_re_runs_a_pair_the_voter_already_judged(db, make_pool):
    players = make_pool(60)
    pairs = list(combinations(players[:12], 2))[::3]
    _record_votes(db, "voter-1", pairs)
    seen = {frozenset({w.id, l.id}) for w, l in pairs}

    for _ in range(400):
        _, a, b = matchmaking.create_matchup(db, "nfl", position="QB", session_id="voter-1")
        assert frozenset({a.id, b.id}) not in seen
    db.commit()


def test_consolidation_pairs_neighbours_in_the_voters_own_order(db, make_pool):
    """The voter's ladder decides who is adjacent, not the global one."""
    players = make_pool(10)
    pool = [(p, db.get(PlayerRating, p.id)) for p in players]

    # Personal order is the reverse of the global one, so a pair that is close
    # globally is far apart personally and vice versa.
    for i, (_, rating) in enumerate(pool):
        rating.rating = 1500.0 + i * 100
    personal = {player.id: 1500.0 - i * 100 for i, (player, _) in enumerate(pool)}
    order = [player.id for player in sorted(players, key=lambda p: personal[p.id], reverse=True)]

    history = [(a.id, b.id) for a, b in zip(players, players[1:])]

    for _ in range(100):
        (a, _), (b, _) = matchmaking._pick_ranked_pair(pool, history, personal)
        assert abs(order.index(a.id) - order.index(b.id)) <= matchmaking.RANKED_PAIR_SPAN


def test_consolidation_leans_on_the_top_of_the_voters_list(db, make_pool):
    """A list is read from the top, and that is where an unbeaten pile-up shows."""
    players = make_pool(60)
    pool = [(p, db.get(PlayerRating, p.id)) for p in players]
    personal = {p.id: 2000.0 - i for i, p in enumerate(players)}
    history = [(a.id, b.id) for a, b in zip(players[::2], players[1::2])]
    top_ten = {p.id for p in players[:10]}

    from_top = sum(
        any(pr[0].id in top_ten for pr in matchmaking._pick_ranked_pair(pool, history, personal))
        for _ in range(400)
    )
    # An even draw over 60 ranked players would touch the top ten about a third
    # of the time; the weighting should land there far more often than that.
    assert from_top / 400 > 0.55


def test_a_voter_with_no_history_is_never_offered_a_ranked_pair(db, pool):
    assert matchmaking._pick_ranked_pair(
        [(p, db.get(PlayerRating, p.id)) for p in pool], [], {}
    ) is None


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
