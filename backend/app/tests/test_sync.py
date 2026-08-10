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


def _stub_get(monkeypatch, by_season, projections=None, stats=None):
    """Serve the three upstream calls a fetch makes, each from a {season: rows}.

    Returns the seasons the roster call was asked for, in order.
    """
    calls = []

    def fake_get(self, path, **params):
        if path.startswith("/projections/season/"):
            season = int(path.rsplit("/", 1)[1])
            return {"data": (projections or {}).get(season, [])}
        if path == "/players/stats":
            return {"data": (stats or {}).get(params["season"], [])}
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


def _projection_row(player_id="00-0001", total_points=120.0):
    return {"player_id": player_id, "total_points": total_points}


def test_players_carry_the_score_that_says_whether_they_will_play(monkeypatch):
    _stub_get(
        monkeypatch,
        {2026: [_roster_row("00-0001"), _roster_row("00-0002")]},
        projections={2026: [_projection_row("00-0001", 148.5)]},
    )

    players = {p.external_id: p for p in nfl.NFLSource().fetch_players(season=2026)}

    assert players["00-0001"].usage == 148.5
    # Nobody projected him, which is itself the answer.
    assert players["00-0002"].usage is None


def test_a_season_nobody_has_projected_still_syncs(monkeypatch):
    """Rosters get published before anyone projects them; that is not an outage."""
    _stub_get(monkeypatch, {2026: [_roster_row()]}, projections={})

    players = nfl.NFLSource().fetch_players(season=2026)

    assert [p.usage for p in players] == [None]


def test_upstream_losing_the_projections_does_not_fail_the_sync(monkeypatch):
    import httpx

    def fake_get(self, path, **params):
        if path.startswith("/projections/") or path == "/players/stats":
            raise httpx.ConnectError("upstream down")
        return {"season": 2026, "data": [_roster_row()]}

    monkeypatch.setattr(nfl.NFLSource, "_get", fake_get)

    assert [p.usage for p in nfl.NFLSource().fetch_players(season=2026)] == [None]


def _stat_row(player_id, fantasy_points, season_type="REG"):
    return {"player_id": player_id, "fantasy_points": fantasy_points, "season_type": season_type}


def test_a_player_the_model_is_sour_on_is_rescued_by_what_he_actually_did(monkeypatch):
    """A projection is an opinion; having been on the field is a fact."""
    _stub_get(
        monkeypatch,
        {2026: [_roster_row(f"00-star-{i}") for i in range(5)] + [_roster_row("00-vet")]},
        # The model likes the five stars and is cold on the veteran.
        projections={
            2026: [_projection_row(f"00-star-{i}", 200.0 - i) for i in range(5)]
            + [_projection_row("00-vet", 3.0)]
        },
        # Last season the veteran outproduced everyone but the best of them.
        stats={
            2025: [_stat_row("00-star-0", 260.0), _stat_row("00-vet", 240.0)]
            + [_stat_row(f"00-star-{i}", 20.0) for i in (1, 2, 3, 4)]
        },
    )

    players = {p.external_id: p for p in nfl.NFLSource().fetch_players(season=2026)}

    # Second-best last season, so he is worth the second-best projection —
    # ahead of every star the model ranked above him but one.
    assert players["00-vet"].usage == 199.0
    assert players["00-star-0"].usage == 200.0


def test_last_season_never_drags_a_well_projected_player_down(monkeypatch):
    """A rookie's projection stands; a star's bad season does not demote him."""
    _stub_get(
        monkeypatch,
        {2026: [_roster_row("00-rookie"), _roster_row("00-star")]},
        projections={2026: [_projection_row("00-rookie", 90.0), _projection_row("00-star", 180.0)]},
        stats={2025: [_stat_row("00-star", 12.0)]},
    )

    players = {p.external_id: p for p in nfl.NFLSource().fetch_players(season=2026)}

    assert players["00-star"].usage == 180.0  # not demoted to the lower scale slot
    assert players["00-rookie"].usage == 90.0  # no last season to read


def test_the_postseason_is_not_counted_as_playing_time(monkeypatch):
    """Only twelve teams get one, so it would flatter whoever made the bracket."""
    _stub_get(
        monkeypatch,
        {2026: [_roster_row("00-0001"), _roster_row("00-0002")]},
        projections={2026: [_projection_row("00-0001", 100.0), _projection_row("00-0002", 20.0)]},
        stats={2025: [_stat_row("00-0002", 400.0, season_type="POST")]},
    )

    players = {p.external_id: p for p in nfl.NFLSource().fetch_players(season=2026)}

    assert players["00-0002"].usage == 20.0


def test_last_season_is_read_from_last_season(monkeypatch):
    """Reading this season's own stats would be empty in August and circular later."""
    seasons = []

    def fake_get(self, path, **params):
        if path.startswith("/projections/season/"):
            return {"data": []}
        if path == "/players/stats":
            seasons.append(params["season"])
            return {"data": []}
        return {"season": 2026, "data": [_roster_row()]}

    monkeypatch.setattr(nfl.NFLSource, "_get", fake_get)
    nfl.NFLSource().fetch_players(season=2026)

    assert set(seasons) == {2025}


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


def test_sync_stores_the_usage_score(db, monkeypatch):
    _use_source(
        monkeypatch,
        [
            SourcePlayer(
                external_id="00-0039075",
                name="Puka Nacua",
                position="WR",
                team_abbr="LA",
                season=2026,
                usage=163.9,
            )
        ],
    )

    sync_module.sync_players(db, "nfl")

    assert db.query(Player).one().usage == 163.9


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
