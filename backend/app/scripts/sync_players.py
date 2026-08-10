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

from database.migrate import ensure_columns  # noqa: E402
from database.models import Base  # noqa: E402
from database.session import SessionLocal, engine  # noqa: E402
from services.sources.base import SourceUnavailable  # noqa: E402
from services.sync import sync_league  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync players for a league")
    parser.add_argument("--league", default="nfl")
    parser.add_argument("--season", type=int, default=None)
    args = parser.parse_args()

    Base.metadata.create_all(engine)
    # The sync writes usage scores, so the column has to exist even if the API
    # process that normally adds it has not restarted yet.
    ensure_columns(engine)

    with SessionLocal() as db:
        try:
            result = sync_league(db, args.league.lower(), season=args.season)
        except SourceUnavailable as exc:
            # Nothing was written. Failing loudly lets the CronJob retry rather
            # than recording a success that quietly changed nothing.
            logging.error("sync aborted: %s", exc)
            return 1

    print(
        f"{result['league']} {result['season']}: {result['fetched']} in pool "
        f"({result['created']} new, {result['updated']} updated, "
        f"{result['deactivated']} deactivated, {result['ratings_seeded']} ratings seeded)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
