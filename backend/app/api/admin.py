#!/usr/bin/env python3
"""Operational endpoints. Gated by a shared token, not user auth."""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from database.session import get_db
from services.sync import sync_league

logger = logging.getLogger(__name__)
router = APIRouter()

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")


def require_admin(x_admin_token: Optional[str] = Header(None)) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is not configured")
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=403, detail="bad admin token")


@router.post("/sync", dependencies=[Depends(require_admin)])
def run_sync(
    league: str = Query("nfl"),
    season: Optional[int] = Query(None, description="Defaults to the source's current season"),
    db: Session = Depends(get_db),
):
    """Refresh a league's teams and player pool from its upstream source."""
    try:
        return {"status": "success", **sync_league(db, league.lower(), season=season)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("sync failed")
        raise HTTPException(status_code=502, detail=f"sync failed: {exc}")
