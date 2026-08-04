#!/usr/bin/env python3
"""
Refresh a league's player pool.

    python app/scripts/sync_players.py --league nfl
    python app/scripts/sync_players.py --league nfl --season 2025

Safe to run repeatedly; intended for a nightly CronJob in-season.
"""

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database.models import Base  # noqa: E402
from database.session import SessionLocal, engine  # noqa: E402
from services.sync import sync_league  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync players for a league")
    parser.add_argument("--league", default="nfl")
    parser.add_argument("--season", type=int, default=None)
    args = parser.parse_args()

    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        result = sync_league(db, args.league.lower(), season=args.season)

    print(
        f"{result['league']}: {result['fetched']} in pool "
        f"({result['created']} new, {result['updated']} updated, "
        f"{result['deactivated']} deactivated, {result['ratings_seeded']} ratings seeded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
