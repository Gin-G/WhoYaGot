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

# --- Ratings ----------------------------------------------------------------
ELO_BASE = float(os.getenv("ELO_BASE", "1500"))
