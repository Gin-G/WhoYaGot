#!/usr/bin/env python3
"""
Team colours, which are data rather than something a feed can be asked for.

The NFL's upstream ships them with the rest of a club's row. MLB's does not —
the Stats API knows everything about a team except what colour it is — and the
leagues after it will be one or the other. So the ones nobody serves live here,
in one place, keyed by the abbreviation that league's own feed uses. That is
not always the one a fan would write: Arizona's baseball club answers to AZ.

They matter more than decoration. Two clubs on a stage are told apart by their
colours before either name is read, and a league without them is two grey
rectangles asking a question.

Adding a league is adding a dict. Nothing here is a fallback for a feed that
already answers — a club keeps whatever its own source gave it, and these only
fill the gaps.
"""

from typing import Iterable, Optional

from services.sources.base import SourceTeam

COLOURS: dict[str, dict[str, tuple[str, str]]] = {
    # MLB's Stats API serves no colours at all, so all thirty are on file.
    "mlb": {
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
    },
}


def colours_for(league: str, abbr: str) -> tuple[Optional[str], Optional[str]]:
    """The primary and secondary on file, or a pair of Nones."""
    return COLOURS.get(league.lower(), {}).get(abbr.upper(), (None, None))


def paint(league: str, teams: Iterable[SourceTeam]) -> list[SourceTeam]:
    """Fill in any colour the league's own feed did not supply.

    The feed wins where it answered: a club that ships its own colours is
    describing itself, and this file is only ever a stand-in for one that does
    not.
    """
    painted = []
    for team in teams:
        if team.color is None or team.color2 is None:
            primary, secondary = colours_for(league, team.abbr)
            team.color = team.color or primary
            team.color2 = team.color2 or secondary
        painted.append(team)
    return painted


def missing(league: str, abbrs: Iterable[str]) -> list[str]:
    """Which of these clubs have no colour on file and none of their own.

    Exists so a test can name them before a deploy does.
    """
    known = COLOURS.get(league.lower(), {})
    return sorted({a.upper() for a in abbrs} - set(known))
