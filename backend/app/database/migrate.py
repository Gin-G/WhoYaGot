#!/usr/bin/env python3
"""
Bring an existing database up to the current models.

`create_all` builds missing tables but never touches a table that already
exists, so a column added to a model is invisible to every deployment that ran
before it. This adds those columns in place.

Deliberately small: only nullable, unindexed additions, which need no backfill
and no downtime, and which an older process can keep running against. Anything
beyond that — a drop, a rename, a type change, an index — wants a real migration
tool, and is the signal to reach for one rather than to grow this file.
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from database.models import Base

logger = logging.getLogger(__name__)

# (table, column) pairs this codebase expects to add to deployments that predate
# them. Types are read from the models, so they cannot drift apart.
ADDED_COLUMNS = (("players", "usage"),)


def ensure_columns(engine: Engine) -> list[str]:
    """Add any missing nullable column. Returns what it added."""
    inspector = inspect(engine)
    added = []

    for table_name, column_name in ADDED_COLUMNS:
        if not inspector.has_table(table_name):
            continue  # create_all is about to build it complete
        if any(c["name"] == column_name for c in inspector.get_columns(table_name)):
            continue

        column = Base.metadata.tables[table_name].columns[column_name]
        ddl = column.type.compile(engine.dialect)
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))

        logger.info("migrate: added %s.%s (%s)", table_name, column_name, ddl)
        added.append(f"{table_name}.{column_name}")

    return added
