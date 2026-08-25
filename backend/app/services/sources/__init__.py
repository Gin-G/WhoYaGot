#!/usr/bin/env python3
"""League source registry. Importing a source module registers it."""

from services.sources.base import (  # noqa: F401
    PlayerSource,
    SourcePlayer,
    SourceTeam,
    all_sources,
    get_source,
    register,
)
from services.sources import mlb  # noqa: F401  (registers "mlb")
from services.sources import nfl  # noqa: F401  (registers "nfl")

__all__ = [
    "PlayerSource",
    "SourcePlayer",
    "SourceTeam",
    "all_sources",
    "get_source",
    "register",
]
