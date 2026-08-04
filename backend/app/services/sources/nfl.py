#!/usr/bin/env python3
"""
NFL source, backed by the NFL-API service (nfl-api.nickknows.net).

That API already dedupes weekly roster rows down to each player's latest week,
so a single call per position is all we need.
"""

import logging
import os
from typing import Optional

import httpx

from config import NFL_API_URL, UPSTREAM_TIMEOUT
from services.sources.base import PlayerSource, SourcePlayer, SourceTeam, register

logger = logging.getLogger(__name__)

# Roster `status` values worth putting in front of a voter. DEV is practice
# squad, RES is injured/reserve, CUT and RET speak for themselves.
POOL_STATUSES = {
    s.strip().upper() for s in os.getenv("NFL_POOL_STATUSES", "ACT").split(",") if s.strip()
}


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
        # A handful of players are listed at two positions in different weeks
        # (a TE taking RB snaps, say). Upstream dedupes within a position but
        # cannot across them, so keep whichever listing is most recent.
        best: dict[str, tuple[int, SourcePlayer]] = {}

        for position in self.positions:
            params = {"position": position}
            if season is not None:
                params["season"] = season

            payload = self._get("/players/rosters", **params)
            resolved_season = payload.get("season")
            rows = payload.get("data", [])

            kept = 0
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
                    ),
                )
                kept += 1

            logger.info("nfl: %s -> %d/%d players in pool", position, kept, len(rows))

        return [player for _, player in best.values()]


register(NFLSource())
