#!/usr/bin/env python3
"""
Runtime configuration, read from the environment with dev-friendly defaults.
"""

import os


def _csv(name: str, default: str) -> list[str]:
    return [v.strip() for v in os.getenv(name, default).split(",") if v.strip()]


# --- Database ---------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./whoyagot_dev.db")

# --- Auth -------------------------------------------------------------------
# Google OAuth client ID. The web client ID must be listed here; Android builds
# using a separate OAuth client need that ID listed too, since Google issues the
# ID token with the client that requested it in the `aud` claim.
GOOGLE_CLIENT_IDS = _csv("GOOGLE_CLIENT_IDS", "")

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_DAYS = int(os.getenv("JWT_TTL_DAYS", "30"))

# --- Upstream data sources --------------------------------------------------
NFL_API_URL = os.getenv("NFL_API_URL", "https://nfl-api.nickknows.net")
UPSTREAM_TIMEOUT = float(os.getenv("UPSTREAM_TIMEOUT", "30"))

# --- CORS -------------------------------------------------------------------
# Capacitor serves the Android webview from https://localhost, so it needs an
# explicit entry — it is a distinct origin from the dev server.
CORS_ORIGINS = _csv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:4173,https://localhost,capacitor://localhost",
)

# --- What counts as ranked --------------------------------------------------
# A rating built from two votes is noise. Hide players below this on the global
# board (their rating still exists and still moves — it just isn't ranked yet).
MIN_VOTES_GLOBAL = int(os.getenv("MIN_VOTES_GLOBAL", "5"))

# The same idea for one person's board, at a threshold their own voting can
# actually reach: a personal ladder is fed by one voter rather than all of them,
# so the global bar would leave a new board empty for hundreds of picks.
#
# In config rather than beside the endpoint because the matchmaker needs it too:
# dialling in a stretch of a board works on the board the voter can see, and a
# player under this bar is not on it.
MIN_VOTES_PERSONAL = int(os.getenv("MIN_VOTES_PERSONAL", "3"))

# --- Ratings ----------------------------------------------------------------
ELO_BASE = float(os.getenv("ELO_BASE", "1500"))
