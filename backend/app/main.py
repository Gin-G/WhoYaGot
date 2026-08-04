#!/usr/bin/env python3
"""
WhoYaGot API — player-vs-player preference voting.

Player data comes from per-league source adapters (NFL first, via NFL-API);
votes, Elo ratings, and user lists live here.
"""

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from api.admin import router as admin_router
from api.auth import router as auth_router
from api.leagues import router as leagues_router
from api.matchups import router as matchups_router
from api.players import router as players_router
from api.rankings import router as rankings_router
from config import CORS_ORIGINS, GOOGLE_CLIENT_IDS, JWT_SECRET

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from database.models import Base
    from database.session import engine

    Base.metadata.create_all(engine)
    logger.info("DB tables verified/created.")
except Exception as db_startup_err:
    logger.warning("DB unavailable at startup (tables not created): %s", db_startup_err)

if not GOOGLE_CLIENT_IDS:
    logger.warning("GOOGLE_CLIENT_IDS unset — sign-in will fail; anonymous voting still works.")
if JWT_SECRET == "dev-secret-change-me":
    logger.warning("JWT_SECRET is the built-in default. Set a real one before deploying.")


class ProxySchemeMiddleware:
    """Trust X-Forwarded-Proto from nginx ingress so redirect URLs use https://."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            proto = headers.get(b"x-forwarded-proto", b"").decode()
            if proto in ("https", "http"):
                scope = dict(scope)
                scope["scheme"] = proto
        await self.app(scope, receive, send)


app = FastAPI(
    title="WhoYaGot API",
    description="Player-vs-player preference voting across leagues",
    version="0.1.0",
)

app.add_middleware(ProxySchemeMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leagues_router, prefix="/leagues", tags=["leagues"])
app.include_router(matchups_router, prefix="/matchups", tags=["matchups"])
app.include_router(rankings_router, prefix="/rankings", tags=["rankings"])
app.include_router(players_router, prefix="/players", tags=["players"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.get("/")
async def root():
    return {
        "message": "WhoYaGot API",
        "version": "0.1.0",
        "status": "running",
        "endpoints": {
            "leagues": "/leagues",
            "next_matchup": "/matchups/next?league=nfl",
            "vote": "POST /matchups/vote",
            "rankings": "/rankings?league=nfl",
            "my_list": "/rankings/me?league=nfl",
            "docs": "/docs",
            "health": "/health",
        },
    }


@app.get("/health")
async def health_check():
    from sqlalchemy import text

    from database.session import SessionLocal

    db_ok = True
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("health check DB probe failed: %s", exc)
        db_ok = False

    return {
        "status": "healthy" if db_ok else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "up" if db_ok else "down",
        "google_auth_configured": bool(GOOGLE_CLIENT_IDS),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
