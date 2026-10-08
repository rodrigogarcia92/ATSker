"""Migration 0017 is reversible (PRD §6, N8.13).

Loaded by path and exercised against SQLite, as `test_migration_0015` does: the
column is added to a populated `llm_calls` table without touching its rows, and
the downgrade removes it.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "0017_llm_calls_latency.py"
)
_spec = importlib.util.spec_from_file_location("migration_0017", _MIGRATION_PATH)
assert _spec is not None and _spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIGRATION)


def _connect():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.execute(
        sa.text("CREATE TABLE llm_calls (id CHAR(32) NOT NULL PRIMARY KEY)")
    )
    return connection


def test_upgrade_then_downgrade_leaves_no_trace():
    connection = _connect()
    connection.execute(
        sa.text("INSERT INTO llm_calls (id) VALUES ('11111111111111111111111111111111')")
    )
    MIGRATION.op = Operations(MigrationContext.configure(connection))

    MIGRATION.upgrade()

    inspector = sa.inspect(connection)
    columns = {column["name"] for column in inspector.get_columns("llm_calls")}
    assert "latency_ms" in columns
    rows = connection.execute(sa.text("SELECT id, latency_ms FROM llm_calls")).all()
    assert rows == [("11111111111111111111111111111111", None)]

    MIGRATION.downgrade()

    columns = {column["name"] for column in sa.inspect(connection).get_columns("llm_calls")}
    assert "latency_ms" not in columns
    connection.close()
