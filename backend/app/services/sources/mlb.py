#!/usr/bin/env python3
"""
MLB source, backed by MLB's own Stats API (statsapi.mlb.com).

Public and unauthenticated, unlike the NFL feed, so there is nothing to
configure to make this league work — but it answers in baseball's own terms
rather than fantasy's, and most of what follows is the translation.

Three calls' worth of shape: the team list, one active roster per club, and
then the players themselves in batches with a season of stats hydrated onto
them. Batching matters — asked one at a time this would be eight hundred
round trips a night instead of forty-odd.
"""

import logging
import os
from datetime import date
from typing import Iterable, Optional

import httpx

from config import UPSTREAM_TIMEOUT
from services.sources.base import (
    PlayerSource,
    SourcePlayer,
    SourceTeam,
    SourceUnavailable,
    register,
)

logger = logging.getLogger(__name__)

API = os.getenv("MLB_API_URL", "https://statsapi.mlb.com/api/v1")

# How many players one /people call is asked for. The endpoint takes a list and
# the URL is the only real limit; fifty keeps it comfortably short.
BATCH = 50

# Baseball fields nine positions and fantasy drafts eight. The three outfield
# spots are one job as far as an argument about them goes — nobody asks whether
# they would rather have a left fielder or a right fielder — so they collapse.
#
# TWP is a two-way player. There is one of him, and he is a hitter who also
# pitches: ranking Ohtani against starters would ask a question about a third
# of his season.
POSITIONS = {
    "C": "C",
    "1B": "1B",
    "2B": "2B",
    "3B": "3B",
    "SS": "SS",
    "LF": "OF",
    "CF": "OF",
    "RF": "OF",
    "OF": "OF",
    "DH": "DH",
    "TWP": "DH",
}

# A pitcher's listed position is just "P", and the split has to come from what
# he has actually done rather than from a label.
#
# Innings per outing rather than share of starts. Erick Fedde started twelve of
# twenty-eight and threw a hundred and eighteen innings — on starts alone he
# reads as a reliever, which is not a thing anyone drafting him would say. What
# separates the jobs is how long a man is left out there: a rotation arm goes
# five or six, a swingman four, and a bullpen arm one. Three splits them and
# puts an opener, who starts by the letter of it and throws an inning, where he
# belongs.
STARTER_INNINGS = 3.0


def _depth(spec: str) -> dict[str, int]:
    """Parse "C=40,OF=120" into a per-position depth."""
    depth = {}
    for entry in spec.split(","):
        position, _, size = entry.partition("=")
        if position.strip() and size.strip().isdigit():
            depth[position.strip().upper()] = int(size)
    return depth


# Roughly two rounds deeper than a 12-team league drafts, so the pool holds
# everyone with a claim without holding the whole of it. Thirty clubs carry
# about 780 active players; this keeps 590 of them.
POOL_DEPTH = _depth(
    os.getenv("MLB_POOL_DEPTH", "C=40,1B=40,2B=40,3B=40,SS=40,OF=120,DH=20,SP=150,RP=100")
)

# What a 12-team league actually takes: two catchers a side, five outfielders,
# a corner and a middle infielder each, and pitching staffs that run deep
# because starts are the scarce thing rather than arms.
CORE_DEPTH = _depth(
    os.getenv("MLB_CORE_DEPTH", "C=24,1B=24,2B=24,3B=24,SS=24,OF=72,DH=12,SP=96,RP=48")
)

SEASON_OVERRIDE = int(os.getenv("MLB_SEASON")) if os.getenv("MLB_SEASON") else None

# The Stats API knows everything about a club except what colour it is. These
# are the primary and secondary each club puts on its own cap and jersey, and
# they exist so a matchup reads as one team against another rather than as two
# grey rectangles. Keyed by the abbreviation the API returns, which is not
# always the one a fan would write — Athletics answer to ATH.
TEAM_COLOURS = {
    "AZ": ("#A71930", "#E3D4AD"),
    "ATH": ("#003831", "#EFB21E"),
    "ATL": ("#CE1141", "#13274F"),
    "BAL": ("#DF4601", "#000000"),
    "BOS": ("#BD3039", "#0C2340"),
    "CHC": ("#0E3386", "#CC3433"),
    "CIN": ("#C6011F", "#000000"),
    "CLE": ("#00385D", "#E50022"),
    "COL": ("#33006F", "#C4CED4"),
    "CWS": ("#27251F", "#C4CED4"),
    "DET": ("#0C2340", "#FA4616"),
    "HOU": ("#002D62", "#EB6E1F"),
    "KC": ("#004687", "#BD9B60"),
    "LAA": ("#BA0021", "#003263"),
    "LAD": ("#005A9C", "#EF3E42"),
    "MIA": ("#00A3E0", "#EF3340"),
    "MIL": ("#12284B", "#FFC52F"),
    "MIN": ("#002B5C", "#D31145"),
    "NYM": ("#002D72", "#FF5910"),
    "NYY": ("#0C2340", "#C4CED3"),
    "PHI": ("#E81828", "#002D72"),
    "PIT": ("#27251F", "#FDB827"),
    "SD": ("#2F241D", "#FFC425"),
    "SEA": ("#0C2C56", "#005C5C"),
    "SF": ("#FD5A1E", "#27251F"),
    "STL": ("#C41E3A", "#0C2340"),
    "TB": ("#092C5C", "#8FBCE6"),
    "TEX": ("#003278", "#C0111F"),
    "TOR": ("#134A8E", "#E8291C"),
    "WSH": ("#AB0003", "#14225A"),
}


def current_season(today: Optional[date] = None) -> int:
    """The season the league is currently in.

    Baseball's year turns over in spring: pitchers and catchers report in
    February and rosters are the coming season's from then on. Before that the
    winter still belongs to the season just finished, which is the one anyone
    arguing in January is arguing about.
    """
    today = today or date.today()
    return today.year if today.month >= 2 else today.year - 1


def _feet_inches(height: Optional[str]) -> Optional[str]:
    """`6' 7"` as `6-7`, which is how the NFL feed writes it."""
    if not height:
        return None
    digits = [part for part in height.replace('"', "").split("'") if part.strip()]
    if len(digits) != 2:
        return None
    feet, inches = digits[0].strip(), digits[1].strip()
    return f"{feet}-{inches}" if feet.isdigit() and inches.isdigit() else None


def _int(value) -> Optional[int]:
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


def _innings(value) -> Optional[float]:
    """Baseball counts thirds of an inning after the point: 118.1 is 118 and a third."""
    if value is None or value == "":
        return None
    whole, _, thirds = str(value).partition(".")
    try:
        outs = int(thirds[:1]) if thirds else 0
        return int(whole) + min(outs, 2) / 3.0
    except ValueError:
        return None


def _stat_groups(person: dict) -> dict[str, dict]:
    """This season's hitting and pitching lines, by group name."""
    lines = {}
    for group in person.get("stats") or []:
        name = (group.get("group") or {}).get("displayName")
        splits = group.get("splits") or []
        if name and splits:
            lines[name] = splits[0].get("stat") or {}
    return lines


def _classify(person: dict) -> tuple[Optional[str], Optional[float]]:
    """The position this player is ranked at, and how much he features there.

    Usage is plate appearances for a hitter and innings for a pitcher. Different
    units, which is fine — it is only ever compared within a position, and
    within one it is the right measure of who is actually playing.
    """
    listed = ((person.get("primaryPosition") or {}).get("abbreviation") or "").upper()
    lines = _stat_groups(person)

    if listed in POSITIONS:
        hitting = lines.get("hitting") or {}
        return POSITIONS[listed], _float(hitting.get("plateAppearances"))

    if listed in {"P", "SP", "RP"}:
        pitching = lines.get("pitching") or {}
        innings = _innings(pitching.get("inningsPitched"))
        games = _int(pitching.get("gamesPlayed")) or 0
        # Listed SP/RP is taken at its word; a bare "P" is judged on his season,
        # and a pitcher with no season yet falls in with the relievers, which is
        # where an unproven arm belongs until he has started something.
        if listed == "P":
            per_outing = (innings or 0.0) / games if games else 0.0
            role = "SP" if per_outing >= STARTER_INNINGS else "RP"
        else:
            role = listed
        return role, innings

    return None, None


class MLBSource(PlayerSource):
    league = "mlb"
    display_name = "MLB"
    positions = ["C", "1B", "2B", "3B", "SS", "OF", "DH", "SP", "RP"]
    pool_depth = POOL_DEPTH
    core_depth = CORE_DEPTH

    def _get(self, client: httpx.Client, path: str, **params) -> dict:
        response = client.get(f"{API}{path}", params=params)
        response.raise_for_status()
        return response.json()

    def fetch_teams(self) -> list[SourceTeam]:
        with httpx.Client(timeout=UPSTREAM_TIMEOUT) as client:
            payload = self._get(client, "/teams", sportId=1)

        teams = payload.get("teams") or []
        if not teams:
            raise SourceUnavailable("MLB returned no teams")

        out = []
        for team in teams:
            abbr = (team.get("abbreviation") or "").upper()
            if not abbr:
                continue
            colour, second = TEAM_COLOURS.get(abbr, (None, None))
            out.append(
                SourceTeam(
                    abbr=abbr,
                    name=team.get("name") or abbr,
                    conference=(team.get("league") or {}).get("name"),
                    division=(team.get("division") or {}).get("name"),
                    color=colour,
                    color2=second,
                    logo_url=f"https://www.mlbstatic.com/team-logos/{team['id']}.svg",
                )
            )

        missing = [t.abbr for t in out if t.color is None]
        if missing:
            # Not fatal: a colourless club still ranks, it just looks plain.
            logger.warning("no colours on file for %s", ", ".join(sorted(missing)))
        return out

    def _rosters(self, client: httpx.Client, team_ids: Iterable[int]) -> dict[int, dict]:
        """Every active player, by id, with the club he is on."""
        rostered: dict[int, dict] = {}
        for team_id in team_ids:
            try:
                payload = self._get(
                    client, f"/teams/{team_id}/roster", rosterType="active"
                )
            except httpx.HTTPError as exc:
                # One club being unreachable is not the league disappearing.
                logger.warning("could not read roster for team %s: %s", team_id, exc)
                continue
            for entry in payload.get("roster") or []:
                person = entry.get("person") or {}
                if person.get("id"):
                    rostered[person["id"]] = entry
        return rostered

    def fetch_players(self, season: Optional[int] = None) -> list[SourcePlayer]:
        season = season or SEASON_OVERRIDE or current_season()

        with httpx.Client(timeout=UPSTREAM_TIMEOUT) as client:
            teams = (self._get(client, "/teams", sportId=1) or {}).get("teams") or []
            by_id = {t["id"]: (t.get("abbreviation") or "").upper() for t in teams}
            rostered = self._rosters(client, by_id)
            if not rostered:
                raise SourceUnavailable("MLB returned no rostered players")

            ids = list(rostered)
            people = []
            for start in range(0, len(ids), BATCH):
                chunk = ids[start : start + BATCH]
                payload = self._get(
                    client,
                    "/people",
                    personIds=",".join(str(i) for i in chunk),
                    hydrate=(
                        "stats(group=[hitting,pitching],type=season,"
                        f"season={season})"
                    ),
                )
                people.extend(payload.get("people") or [])

        players = []
        for person in people:
            position, usage = _classify(person)
            if position is None:
                continue
            entry = rostered.get(person["id"]) or {}
            players.append(
                SourcePlayer(
                    external_id=str(person["id"]),
                    name=person.get("fullName") or "",
                    position=position,
                    team_abbr=by_id.get(entry.get("parentTeamId")),
                    # The "silo" cut is the one on a transparent background.
                    # The default headshot carries a grey studio backdrop, which
                    # on a stage painted in team colours reads as a photograph
                    # stuck to the field rather than a player standing on it.
                    headshot_url=(
                        "https://img.mlbstatic.com/mlb-photos/image/upload/"
                        "w_213,q_auto:best,f_png/v1/people/"
                        f"{person['id']}/headshot/silo/current"
                    ),
                    jersey_number=_int(
                        entry.get("jerseyNumber") or person.get("primaryNumber")
                    ),
                    height=_feet_inches(person.get("height")),
                    weight=_float(person.get("weight")),
                    # Draft year is deliberately left off. The feed gives the
                    # year but never the round or the pick, and the card reads a
                    # year without a pick as undrafted — which said "'15 UDFA"
                    # under a man who went in the third round. A baseball draft
                    # slot is weak signal anyway, six years and three levels
                    # before anyone sees him.
                    birth_date=person.get("birthDate"),
                    season=season,
                    usage=usage,
                )
            )

        if not players:
            raise SourceUnavailable("MLB roster held nobody at a rankable position")
        return players


register(MLBSource())
