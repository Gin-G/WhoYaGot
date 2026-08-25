"""The MLB adapter, and the translation from baseball into a draft board."""

import pytest

from services.sources import get_source, mlb


def _person(pid, name, position, *, hitting=None, pitching=None, **bio):
    stats = []
    if hitting is not None:
        stats.append({"group": {"displayName": "hitting"}, "splits": [{"stat": hitting}]})
    if pitching is not None:
        stats.append({"group": {"displayName": "pitching"}, "splits": [{"stat": pitching}]})
    return {
        "id": pid,
        "fullName": name,
        "primaryPosition": {"abbreviation": position},
        "stats": stats,
        **bio,
    }


def _stub(monkeypatch, teams, roster, people):
    """Answer the three calls fetch_players makes, without a network."""
    calls = []

    def fake_get(self, client, path, **params):
        calls.append((path, params))
        if path == "/teams":
            return {"teams": teams}
        if path.endswith("/roster"):
            team_id = int(path.split("/")[2])
            return {"roster": [r for r in roster if r["parentTeamId"] == team_id]}
        if path == "/people":
            wanted = {int(i) for i in params["personIds"].split(",")}
            return {"people": [p for p in people if p["id"] in wanted]}
        raise AssertionError(f"unexpected call {path}")

    monkeypatch.setattr(mlb.MLBSource, "_get", fake_get)
    return calls


TEAM = {"id": 147, "abbreviation": "NYY", "name": "New York Yankees",
        "league": {"name": "American League"}, "division": {"name": "AL East"}}


def _roster_entry(pid, number="1"):
    return {"person": {"id": pid}, "jerseyNumber": number, "parentTeamId": 147}


# --- reading a season ---------------------------------------------------------


@pytest.mark.parametrize(
    "today,expected",
    [("2026-01-15", 2025), ("2026-02-01", 2026), ("2026-08-24", 2026), ("2026-11-30", 2026)],
)
def test_the_season_turns_over_when_pitchers_report(today, expected):
    from datetime import date

    assert mlb.current_season(date.fromisoformat(today)) == expected


def test_innings_are_counted_in_thirds_not_tenths():
    assert mlb._innings("118.1") == pytest.approx(118 + 1 / 3)
    assert mlb._innings("118.2") == pytest.approx(118 + 2 / 3)
    assert mlb._innings("118.0") == 118.0
    assert mlb._innings(None) is None


def test_height_is_rewritten_the_way_the_other_league_writes_it():
    assert mlb._feet_inches("6' 7\"") == "6-7"
    assert mlb._feet_inches(None) is None
    assert mlb._feet_inches("tall") is None


# --- which position a player is argued about at -------------------------------


@pytest.mark.parametrize("listed,expected", [("LF", "OF"), ("CF", "OF"), ("RF", "OF")])
def test_the_three_outfield_spots_are_one_job(listed, expected):
    position, _ = mlb._classify(_person(1, "X", listed, hitting={"plateAppearances": 500}))
    assert position == expected


def test_a_two_way_player_is_ranked_where_he_plays_every_day():
    """There is one of him, and he hits far more often than he pitches."""
    ohtani = _person(2, "Two Way", "TWP",
                     hitting={"plateAppearances": 554},
                     pitching={"inningsPitched": "85.2", "gamesPlayed": 14, "gamesStarted": 14})
    position, usage = mlb._classify(ohtani)
    assert position == "DH"
    assert usage == 554


def test_a_hitters_usage_is_how_often_he_bats():
    _, usage = mlb._classify(_person(3, "X", "SS", hitting={"plateAppearances": 587}))
    assert usage == 587


def test_a_rotation_arm_is_a_starter():
    position, usage = mlb._classify(
        _person(4, "Ace", "P", pitching={"inningsPitched": "183.2", "gamesPlayed": 28,
                                         "gamesStarted": 28})
    )
    assert position == "SP"
    assert usage == pytest.approx(183 + 2 / 3)


def test_a_swingman_is_judged_on_how_long_he_is_left_out_there(monkeypatch):
    """Twelve starts in twenty-eight, and a hundred and eighteen innings.

    On share of starts he reads as a reliever, which is not a thing anyone
    drafting him would say.
    """
    position, _ = mlb._classify(
        _person(5, "Swing", "P", pitching={"inningsPitched": "118.1", "gamesPlayed": 28,
                                           "gamesStarted": 12})
    )
    assert position == "SP"


def test_a_bullpen_arm_is_a_reliever():
    position, _ = mlb._classify(
        _person(6, "Closer", "P", pitching={"inningsPitched": "62.0", "gamesPlayed": 61,
                                            "gamesStarted": 0})
    )
    assert position == "RP"


def test_an_opener_starts_by_the_letter_of_it_and_is_still_a_reliever():
    position, _ = mlb._classify(
        _person(7, "Opener", "P", pitching={"inningsPitched": "40.0", "gamesPlayed": 30,
                                            "gamesStarted": 25})
    )
    assert position == "RP"


def test_an_arm_with_no_season_yet_waits_in_the_bullpen():
    position, usage = mlb._classify(_person(8, "Rookie", "P"))
    assert position == "RP"
    assert usage is None


def test_a_position_nobody_drafts_is_left_out():
    assert mlb._classify(_person(9, "Coach", "UNKNOWN"))[0] is None


# --- the calls themselves -----------------------------------------------------


def test_players_come_back_with_their_club_and_their_season(monkeypatch):
    people = [_person(100, "Aaron Judge", "RF", hitting={"plateAppearances": 261},
                      height="6' 7\"", weight=282, draftYear=2013, birthDate="1992-04-26")]
    _stub(monkeypatch, [TEAM], [_roster_entry(100, "99")], people)

    players = get_source("mlb").fetch_players(season=2026)
    assert len(players) == 1
    judge = players[0]
    assert (judge.name, judge.position, judge.team_abbr) == ("Aaron Judge", "OF", "NYY")
    assert judge.jersey_number == 99
    assert judge.height == "6-7"
    assert judge.season == 2026
    assert judge.external_id == "100"
    assert "100" in judge.headshot_url


def test_people_are_asked_for_in_batches(monkeypatch):
    """Eight hundred players one at a time would be eight hundred round trips."""
    monkeypatch.setattr(mlb, "BATCH", 2)
    people = [_person(i, f"P{i}", "SS", hitting={"plateAppearances": 400}) for i in range(1, 6)]
    calls = _stub(monkeypatch, [TEAM], [_roster_entry(i) for i in range(1, 6)], people)

    assert len(get_source("mlb").fetch_players(season=2026)) == 5
    people_calls = [c for c in calls if c[0] == "/people"]
    assert len(people_calls) == 3  # 2 + 2 + 1


def test_an_empty_league_is_refused_rather_than_synced(monkeypatch):
    _stub(monkeypatch, [TEAM], [], [])
    with pytest.raises(mlb.SourceUnavailable):
        get_source("mlb").fetch_players(season=2026)


def test_every_club_carries_its_colours(monkeypatch):
    monkeypatch.setattr(
        mlb.MLBSource, "_get",
        lambda self, client, path, **p: {"teams": [TEAM]},
    )
    teams = get_source("mlb").fetch_teams()
    assert len(teams) == 1
    assert teams[0].color == mlb.TEAM_COLOURS["NYY"][0]
    assert teams[0].logo_url.endswith("/147.svg")


def test_the_colour_map_covers_the_whole_league():
    """Thirty clubs, and the API spells Arizona AZ rather than ARI."""
    assert len(mlb.TEAM_COLOURS) == 30
    assert "AZ" in mlb.TEAM_COLOURS


def test_the_pool_is_deeper_than_the_core_at_every_position():
    source = get_source("mlb")
    for position in source.positions:
        assert source.pool_depth[position] > source.core_depth[position], position
