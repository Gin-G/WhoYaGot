#!/usr/bin/env python3
"""
NFL source, backed by the NFL-API service (nfl-api.nickknows.net).

That API already dedupes weekly roster rows down to each player's latest week,
so a single call per position is all we need.
"""

import logging
import os
from datetime import date
from typing import Optional

import httpx

from config import NFL_API_URL, UPSTREAM_TIMEOUT
from services.sources.base import (
    PlayerSource,
    SourcePlayer,
    SourceTeam,
    SourceUnavailable,
    register,
)

logger = logging.getLogger(__name__)

# Roster `status` values worth putting in front of a voter. DEV is practice
# squad, RES is injured/reserve, CUT and RET speak for themselves.
POOL_STATUSES = {
    s.strip().upper() for s in os.getenv("NFL_POOL_STATUSES", "ACT").split(",") if s.strip()
}

# Pins the sync to one season. Empty means work it out from the date, which is
# what you want outside of a backfill.
SEASON_OVERRIDE = int(os.getenv("NFL_SEASON")) if os.getenv("NFL_SEASON") else None


def _depth(spec: str) -> dict[str, int]:
    """Parse "QB=48,RB=64" into a per-position pool depth."""
    depth = {}
    for entry in spec.split(","):
        position, _, size = entry.partition("=")
        if position.strip() and size.strip().isdigit():
            depth[position.strip().upper()] = int(size)
    return depth


# How many players per position actually see the field, which is a fraction of
# an untrimmed 90-man offseason roster: 2026 camp lists 379 WRs and 210 RBs.
#
# The numbers come from 2025 snap counts. Across a sample of teams, the players
# clearing ~350 offensive snaps (a little over 20 a game) worked out to 1.2 QBs,
# 1.0 RBs, 4.0 WRs and 2.2 TEs per team; RB is set above its snap share because
# committee backfields spread real touches over more bodies than snaps suggest.
POOL_DEPTH = _depth(os.getenv("NFL_POOL_DEPTH", "QB=48,RB=64,WR=144,TE=80"))


def current_season(today: Optional[date] = None) -> int:
    """The season year the league is currently in.

    The league year turns over in March, when free agency opens and rosters
    start reflecting the season ahead — so from March onwards the current
    season is this calendar year's, and January and February still belong to
    the season that began the previous autumn.

    Upstream must not be left to decide this. Asked without a season it answers
    with the last *completed* one, which through an entire offseason and well
    into the new year means every team is a year out of date.
    """
    today = today or date.today()
    return today.year if today.month >= 3 else today.year - 1


def _int(value) -> Optional[int]:
    """Upstream sends several numeric fields as floats (jersey 17.0)."""
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float(value) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class NFLSource(PlayerSource):
    league = "nfl"
    display_name = "NFL"
    positions = ["QB", "RB", "WR", "TE"]
    pool_depth = POOL_DEPTH

    def __init__(self, base_url: str = NFL_API_URL):
        self.base_url = base_url.rstrip("/")

    def _get(self, path: str, **params) -> dict:
        with httpx.Client(timeout=UPSTREAM_TIMEOUT) as client:
            resp = client.get(f"{self.base_url}{path}", params=params)
            resp.raise_for_status()
            return resp.json()

    def fetch_teams(self) -> list[SourceTeam]:
        payload = self._get("/teams/")
        teams = []
        for row in payload.get("data", []):
            abbr = row.get("team_abbr")
            if not abbr:
                continue
            teams.append(
                SourceTeam(
                    abbr=abbr,
                    name=row.get("team_name") or abbr,
                    conference=row.get("team_conf"),
                    division=row.get("team_division"),
                    color=row.get("team_color"),
                    color2=row.get("team_color2"),
                    logo_url=row.get("team_logo_espn"),
                    wordmark_url=row.get("team_wordmark"),
                )
            )
        return teams

    def fetch_players(self, season: Optional[int] = None) -> list[SourcePlayer]:
        # An explicit season is taken at face value: a backfill asking for 2019
        # wants 2019, not a helpful substitute.
        if season is not None:
            return self._fetch_season(season)

        target = SEASON_OVERRIDE or current_season()
        try:
            return self._fetch_season(target)
        except SourceUnavailable as exc:
            # Between the March rollover and the first roster publication of a
            # new league year, the season exists on the calendar but not yet in
            # the data. Last season's rosters beat no rosters at all.
            logger.warning(
                "nfl: season %s has no rosters yet (%s) — falling back to %s",
                target,
                exc,
                target - 1,
            )
            return self._fetch_season(target - 1)

    def _projected(self, season: int, position: str) -> dict[str, float]:
        """Projected season fantasy points per player, keyed by gsis id.

        The projection engine covers rookies from draft capital and college
        production, which is the whole point — a rookie has no snaps to look
        back on, and "will he play at all" is exactly what we need to know
        about him.

        A missing projection is not fatal: rosters get published before anyone
        has projected the season, and a player with neither a projection nor a
        record of playing simply does not make the cut.
        """
        try:
            payload = self._get(f"/projections/season/{season}", position=position, limit=1000)
        except httpx.HTTPError as exc:
            logger.warning("nfl: no %s projections for %s (%s)", position, season, exc)
            return {}

        points = {}
        for row in payload.get("data", []):
            player_id = row.get("player_id")
            total = _float(row.get("total_points"))
            if player_id and total is not None:
                points[player_id] = total
        return points

    def _produced(self, season: int, position: str) -> dict[str, float]:
        """What each player actually did last season, keyed by gsis id.

        A projection is one model's opinion of a season nobody has played yet,
        and it can be sour on a player the whole league knows. Someone who
        really was on the field is worth ranking whatever the model makes of
        his next season, so last season gets a vote of its own.

        This started as cover for an upstream bug that had Kamara 70th among
        backs and Godwin 149th among receivers. That bug is fixed and both now
        project where they belong, but the reason to keep reading last season
        outlived it: a model can only be wrong about a projection, while having
        taken real snaps is a fact.

        Weekly rows, so they are summed per player. Postseason is left out —
        it is only available to the twelve teams that got there.
        """
        try:
            payload = self._get("/players/stats", season=season, position=position)
        except httpx.HTTPError as exc:
            logger.warning("nfl: no %s stats for %s (%s)", position, season, exc)
            return {}

        points: dict[str, float] = {}
        for row in payload.get("data", []):
            if (row.get("season_type") or "REG").upper() != "REG":
                continue
            player_id = row.get("player_id")
            if player_id:
                points[player_id] = points.get(player_id, 0.0) + (
                    _float(row.get("fantasy_points")) or 0.0
                )
        return points

    def _rate_usage(self, players: list[SourcePlayer], season: int) -> None:
        """Score each player on how much he is likely to be on the field.

        Two answers to that question, and a player deserves the better of them:
        what he is projected to do this season, and what he actually did last
        season. They are not on the same scale — projections are conservative,
        and a season's real points outrun them — so last season is read as a
        finishing position and converted to the projection that a player of
        that standing carries. Comparing where someone placed rather than what
        he scored keeps the two answers honest against each other.

        Rookies have no last season and keep their projection, which is the
        only thing anyone has to go on for them.
        """
        by_position: dict[str, list[SourcePlayer]] = {}
        for player in players:
            by_position.setdefault(player.position, []).append(player)

        for position, group in by_position.items():
            produced = self._produced(season - 1, position)

            # The scale: the projections held by this position's rostered
            # players, best first. Position `k` on it is what a player who
            # finished `k`th last season is worth.
            scale = sorted((p.usage or 0.0 for p in group), reverse=True)
            finishers = sorted(
                (p for p in group if produced.get(p.external_id, 0.0) > 0),
                key=lambda p: -produced[p.external_id],
            )
            earned = {
                player.external_id: scale[place]
                for place, player in enumerate(finishers)
                if place < len(scale)
            }

            for player in group:
                standing = earned.get(player.external_id)
                # Neither projected nor ever on the field: nothing is known
                # about him, which is not the same as knowing he is a zero.
                if player.usage is None and standing is None:
                    continue
                player.usage = max(player.usage or 0.0, standing or 0.0)

    def _fetch_season(self, season: int) -> list[SourcePlayer]:
        # A handful of players are listed at two positions in different weeks
        # (a TE taking RB snaps, say). Upstream dedupes within a position but
        # cannot across them, so keep whichever listing is most recent.
        best: dict[str, tuple[int, SourcePlayer]] = {}
        resolved_season = season

        for position in self.positions:
            payload = self._get("/players/rosters", position=position, season=season)
            resolved_season = payload.get("season") or season
            rows = payload.get("data", [])
            projected_points = self._projected(resolved_season, position)

            # A season past the end of the data answers 200 with an empty list
            # rather than an error. Treated as a real result it would empty the
            # pool, so it has to stop the sync here.
            if not rows:
                raise SourceUnavailable(f"{season} {position}: upstream returned no rows")

            kept = projected = 0
            for row in rows:
                if (row.get("status") or "").upper() not in POOL_STATUSES:
                    continue
                external_id = row.get("player_id")
                name = row.get("player_display_name") or row.get("player_name")
                if not external_id or not name:
                    continue

                week = _int(row.get("week")) or 0
                existing = best.get(external_id)
                if existing is not None and existing[0] >= week:
                    logger.info(
                        "nfl: %s listed at %s (wk %s) and %s (wk %s) — keeping %s",
                        name,
                        existing[1].position,
                        existing[0],
                        position,
                        week,
                        existing[1].position,
                    )
                    continue

                best[external_id] = (
                    week,
                    SourcePlayer(
                        external_id=external_id,
                        name=name,
                        position=position,
                        team_abbr=row.get("team"),
                        headshot_url=row.get("headshot_url"),
                        jersey_number=_int(row.get("jersey_number")),
                        height=row.get("height"),
                        weight=_float(row.get("weight")),
                        college=row.get("college"),
                        years_exp=_int(row.get("years_exp")),
                        draft_year=_int(row.get("entry_year")),
                        draft_number=_int(row.get("draft_number")),
                        birth_date=(row.get("birth_date") or "")[:10] or None,
                        season=resolved_season,
                        usage=projected_points.get(external_id),
                    ),
                )
                kept += 1
                projected += external_id in projected_points

            logger.info(
                "nfl: %s -> %d/%d rostered, %d projected, voting on the top %s",
                position,
                kept,
                len(rows),
                projected,
                self.pool_depth.get(position, "all"),
            )

        players = [player for _, player in best.values()]
        # Last, so a player listed at two positions is scored against the one
        # the dedupe above settled on.
        self._rate_usage(players, resolved_season)
        return players


register(NFLSource())
