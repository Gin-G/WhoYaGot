#!/usr/bin/env python3
"""
The contract every league's data source implements.

Adding a league means writing one of these and registering it — nothing in the
schema, matchmaking, or frontend needs to know which sport it is looking at.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class SourceUnavailable(Exception):
    """Upstream answered, but not with a usable roster.

    Distinct from a transport error: the call succeeded and returned nothing.
    Callers must not read that as "every player left the league".
    """


@dataclass
class SourceTeam:
    abbr: str
    name: str
    conference: Optional[str] = None
    division: Optional[str] = None
    color: Optional[str] = None
    color2: Optional[str] = None
    logo_url: Optional[str] = None
    wordmark_url: Optional[str] = None


@dataclass
class SourcePlayer:
    external_id: str
    name: str
    position: str
    team_abbr: Optional[str] = None
    headshot_url: Optional[str] = None
    jersey_number: Optional[int] = None
    height: Optional[str] = None
    weight: Optional[float] = None
    college: Optional[str] = None
    years_exp: Optional[int] = None
    draft_year: Optional[int] = None
    draft_number: Optional[int] = None
    birth_date: Optional[str] = None
    season: Optional[int] = None


class PlayerSource(ABC):
    """One sport's upstream feed."""

    league: str = ""
    display_name: str = ""
    # Positions that form the matchup pool, in the order the UI should tab them.
    positions: list[str] = []

    @abstractmethod
    def fetch_teams(self) -> list[SourceTeam]:
        """All teams in the league."""

    @abstractmethod
    def fetch_players(self, season: Optional[int] = None) -> list[SourcePlayer]:
        """Every rostered player eligible for the matchup pool."""


_REGISTRY: dict[str, PlayerSource] = {}


def register(source: PlayerSource) -> PlayerSource:
    _REGISTRY[source.league] = source
    return source


def get_source(league: str) -> PlayerSource:
    try:
        return _REGISTRY[league.lower()]
    except KeyError:
        raise ValueError(f"unknown league: {league!r} (have: {', '.join(sorted(_REGISTRY))})")


def all_sources() -> list[PlayerSource]:
    return list(_REGISTRY.values())
