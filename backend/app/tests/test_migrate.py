"""`create_all` will not alter a table that already exists, so this has to."""

from sqlalchemy import create_engine, inspect, text

from database.migrate import ADDED_COLUMNS, ensure_columns
from database.models import Base


def _engine_without(column: str, table: str = "players"):
    """A database built the way a deployment that predates the column has it."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
    return engine


def test_a_column_added_since_the_last_deploy_is_added_in_place():
    engine = _engine_without("usage")

    assert ensure_columns(engine) == ["players.usage"]
    assert "usage" in {c["name"] for c in inspect(engine).get_columns("players")}


def test_the_new_column_is_usable_once_added():
    engine = _engine_without("usage")
    ensure_columns(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO players (league, external_id, name, active, usage) "
                "VALUES ('nfl', '00-1', 'Test Player', 1, 163.9)"
            )
        )
        assert conn.execute(text("SELECT usage FROM players")).scalar() == 163.9


def test_running_it_twice_changes_nothing():
    engine = _engine_without("usage")
    ensure_columns(engine)

    assert ensure_columns(engine) == []


def test_a_fresh_database_needs_no_migrating():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)

    assert ensure_columns(engine) == []


def test_every_declared_column_exists_on_its_model():
    """A typo here would be a silent no-op on every deployment."""
    for table, column in ADDED_COLUMNS:
        assert column in Base.metadata.tables[table].columns


def test_declared_columns_are_addable_in_place():
    """No index and no NOT NULL — this file cannot deliver either."""
    for table, column_name in ADDED_COLUMNS:
        column = Base.metadata.tables[table].columns[column_name]
        assert column.nullable, f"{table}.{column_name} needs a backfill, not this"
        assert not column.index, f"{table}.{column_name} index would never be created"
