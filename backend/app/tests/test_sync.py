"""Season resolution and the guards around a bad upstream answer."""

from datetime import date

import pytest

from database.models import Player, PlayerRating
from services import sync as sync_module
from services.sources import nfl
from services.sources.base import PlayerSource, SourcePlayer, SourceUnavailable


# --- Season resolution ------------------------------------------------------


@pytest.mark.parametrize(
    "today,expected",
    [
        (date(2026, 8, 5), 2026),  # camp
        (date(2026, 3, 1), 2026),  # league year opens
        (date(2026, 2, 28), 2025),  # still last season
        (date(2026, 1, 15), 2025),  # playoffs belong to the season before
        (date(2026, 12, 20), 2026),
    ],
)
def test_current_season_rolls_over_in_march(today, expected):
    assert nfl.current_season(today) == expected


# --- Source behaviour -------------------------------------------------------


def _roster_row(player_id="00-0001", team="MIA", week=1):
    return {
        "player_id": player_id,
        "player_display_name": "Test Player",
        "team": team,
        "status": "ACT",
        "week": week,
    }


def _stub_get(monkeypatch, by_season):
    """Serve /players/rosters from a {season: rows} mapping."""
    calls = []

    def fake_get(self, path, **params):
        season = params["season"]
        calls.append(season)
        return {"season": season, "data": by_season.get(season, [])}

    monkeypatch.setattr(nfl.NFLSource, "_get", fake_get)
    return calls


def test_fetch_players_uses_the_current_season(monkeypatch):
    monkeypatch.setattr(nfl, "SEASON_OVERRIDE", None)
    monkeypatch.setattr(nfl, "current_season", lambda today=None: 2026)
    _stub_get(monkeypatch, {2026: [_roster_row(team="MIA")]})

    players = nfl.NFLSource().fetch_players()

    assert {p.team_abbr for p in players} == {"MIA"}
    assert {p.season for p in players} == {2026}


def test_fetch_players_falls_back_when_the_new_season_is_unpublished(monkeypatch):
    monkeypatch.setattr(nfl, "SEASON_OVERRIDE", None)
    monkeypatch.setattr(nfl, "current_season", lambda today=None: 2027)
    calls = _stub_get(monkeypatch, {2026: [_roster_row(team="GB")]})

    players = nfl.NFLSource().fetch_players()

    assert calls[0] == 2027  # asked for the new one first
    assert {p.season for p in players} == {2026}


def test_an_explicit_season_does_not_fall_back(monkeypatch):
    _stub_get(monkeypatch, {2026: [_roster_row()]})

    with pytest.raises(SourceUnavailable):
        nfl.NFLSource().fetch_players(season=2030)


def test_season_override_wins(monkeypatch):
    monkeypatch.setattr(nfl, "SEASON_OVERRIDE", 2024)
    monkeypatch.setattr(nfl, "current_season", lambda today=None: 2026)
    _stub_get(monkeypatch, {2024: [_roster_row()]})

    assert {p.season for p in nfl.NFLSource().fetch_players()} == {2024}


# --- Sync guards ------------------------------------------------------------


class _FakeSource(PlayerSource):
    league = "nfl"
    positions = ["QB"]

    def __init__(self, players):
        self._players = players

    def fetch_teams(self):
        return []

    def fetch_players(self, season=None):
        return self._players


def _use_source(monkeypatch, players):
    monkeypatch.setattr(sync_module, "get_source", lambda league: _FakeSource(players))


def test_sync_refuses_to_empty_the_pool(db, monkeypatch, pool):
    _use_source(monkeypatch, [])

    with pytest.raises(SourceUnavailable):
        sync_module.sync_players(db, "nfl")

    assert db.query(Player).filter(Player.active.is_(True)).count() == len(pool)


def test_sync_updates_a_traded_player(db, monkeypatch):
    db.add(
        Player(
            league="nfl",
            external_id="00-0038128",
            name="Malik Willis",
            position="QB",
            team_abbr="GB",
            season=2025,
            active=True,
        )
    )
    db.commit()

    _use_source(
        monkeypatch,
        [
            SourcePlayer(
                external_id="00-0038128",
                name="Malik Willis",
                position="QB",
                team_abbr="MIA",
                season=2026,
            )
        ],
    )

    result = sync_module.sync_players(db, "nfl")

    player = db.query(Player).filter(Player.external_id == "00-0038128").one()
    assert player.team_abbr == "MIA"
    assert player.season == 2026
    assert result["season"] == 2026
    assert result["created"] == 0


def test_players_absent_from_a_real_fetch_still_deactivate(db, monkeypatch, pool):
    """The guard must not block ordinary roster churn — only an empty answer."""
    survivor = pool[0]
    _use_source(
        monkeypatch,
        [
            SourcePlayer(
                external_id=survivor.external_id,
                name=survivor.name,
                position="QB",
                team_abbr="BUF",
                season=2026,
            )
        ],
    )

    result = sync_module.sync_players(db, "nfl")

    assert result["deactivated"] == len(pool) - 1
    assert db.query(Player).filter(Player.active.is_(True)).count() == 1
    assert db.query(PlayerRating).count() == len(pool)  # ratings survive
