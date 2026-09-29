"""Migration 0014 is reversible (PRD F10.8, A8).

The migration is exercised against SQLite — the same schema store the rest of the
suite builds — by binding `alembic.op` to a live connection and calling the module's
`upgrade()`/`downgrade()` directly. A8 makes that possible: the types are
dialect-neutral and the partial unique index carries both `postgresql_where` and
`sqlite_where`, so the same DDL runs where the tests run.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

# Loaded by path: the migrations directory is Alembic's script tree, not an
# importable package.
_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0014_application_attempts.py"
)
_spec = importlib.util.spec_from_file_location("migration_0014", _MIGRATION_PATH)
assert _spec is not None and _spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIGRATION)


def _connect():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    # `upgrade()` adds a column to `applications` and references `profiles`, so both
    # must exist before it runs. SQLite does not enforce the foreign keys, so the
    # stubs need no columns beyond the key.
    connection.execute(sa.text("CREATE TABLE profiles (id CHAR(32) NOT NULL PRIMARY KEY)"))
    connection.execute(
        sa.text("CREATE TABLE applications (id CHAR(32) NOT NULL PRIMARY KEY)")
    )
    return connection


def _bind(connection) -> None:
    """Point the migration module's `op` at this connection, as Alembic would."""
    MIGRATION.op = Operations(MigrationContext.configure(connection))


def _columns(connection, table: str) -> set[str]:
    inspector = sa.inspect(connection)
    return {column["name"] for column in inspector.get_columns(table)}


def _indexes(connection, table: str) -> set[str]:
    inspector = sa.inspect(connection)
    return {index["name"] for index in inspector.get_indexes(table)}


def test_upgrade_then_downgrade_leaves_no_trace_on_a_clean_database():
    connection = _connect()
    _bind(connection)

    MIGRATION.upgrade()

    assert "application_attempts" in sa.inspect(connection).get_table_names()
    attempts = _columns(connection, "application_attempts")
    # A8's two additions sit beside the spec's columns.
    assert {"status", "error"} <= attempts
    assert {"report", "file_sha256", "is_sent", "token_cost_usd"} <= attempts
    assert "uq_application_attempt_sent" in _indexes(connection, "application_attempts")
    assert "sent_attempt_id" in _columns(connection, "applications")

    MIGRATION.downgrade()

    assert "application_attempts" not in sa.inspect(connection).get_table_names()
    assert "sent_attempt_id" not in _columns(connection, "applications")
    connection.close()


def test_upgrade_is_idempotent_over_an_existing_row_set():
    """The migration adds the FK-bearing column to a populated `applications` table
    without touching the rows already there (additive, A8)."""
    connection = _connect()
    connection.execute(
        sa.text("INSERT INTO applications (id) VALUES ('11111111111111111111111111111111')")
    )
    _bind(connection)

    MIGRATION.upgrade()

    rows = connection.execute(sa.text("SELECT id, sent_attempt_id FROM applications")).all()
    assert rows == [("11111111111111111111111111111111", None)]
    connection.close()
