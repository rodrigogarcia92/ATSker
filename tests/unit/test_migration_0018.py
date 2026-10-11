"""Migration 0018 is reversible (PRD F11.10).

Exercised against SQLite as `test_migration_0014` is: the module's `upgrade()` and
`downgrade()` run on a live connection holding stub tables with a few rows, so the
test shows that nothing existing is touched and that the downgrade survives a CV that
has no file bytes.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "migrations" / "versions" / "0018_analysis_on_a_cv.py"
)
_spec = importlib.util.spec_from_file_location("migration_0018", _MIGRATION_PATH)
assert _spec is not None and _spec.loader is not None
MIGRATION = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(MIGRATION)

APPLICATION = "11111111111111111111111111111111"
RESUME = "22222222222222222222222222222222"


def _connect():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.execute(
        sa.text("CREATE TABLE application_attempts (id CHAR(32) NOT NULL PRIMARY KEY)")
    )
    connection.execute(sa.text("CREATE TABLE applications (id CHAR(32) NOT NULL PRIMARY KEY)"))
    connection.execute(
        sa.text(
            "CREATE TABLE resumes (id CHAR(32) NOT NULL PRIMARY KEY, "
            "filename VARCHAR(255) NOT NULL, file_bytes BLOB NOT NULL)"
        )
    )
    connection.execute(sa.text(f"INSERT INTO applications (id) VALUES ('{APPLICATION}')"))
    connection.execute(
        sa.text(
            "INSERT INTO resumes (id, filename, file_bytes) "
            f"VALUES ('{RESUME}', 'a.docx', x'0102')"
        )
    )
    return connection


def _bind(connection) -> None:
    MIGRATION.op = Operations(MigrationContext.configure(connection))


def _columns(connection, table: str) -> dict[str, dict]:
    return {column["name"]: column for column in sa.inspect(connection).get_columns(table)}


def _indexes(connection, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(connection).get_indexes(table)}


def test_upgrade_adds_the_columns_and_keeps_the_rows():
    connection = _connect()
    _bind(connection)

    MIGRATION.upgrade()

    resumes = _columns(connection, "resumes")
    assert "source_attempt_id" in resumes
    assert resumes["file_bytes"]["nullable"] is True
    assert "ix_resumes_source_attempt_id" in _indexes(connection, "resumes")
    applications = _columns(connection, "applications")
    assert "resume_id" in applications and applications["resume_id"]["nullable"] is True
    assert "ix_applications_resume_id" in _indexes(connection, "applications")

    rows = connection.execute(sa.text("SELECT id, resume_id FROM applications")).all()
    assert rows == [(APPLICATION, None)], "no backfill: an old application keeps NULL (F11.8)"
    kept = connection.execute(sa.text("SELECT filename, file_bytes FROM resumes")).all()
    assert kept == [("a.docx", b"\x01\x02")]
    connection.close()


def test_the_new_foreign_keys_set_null_on_delete():
    connection = _connect()
    _bind(connection)

    MIGRATION.upgrade()

    inspector = sa.inspect(connection)
    on_delete = {
        (fk["referred_table"], tuple(fk["constrained_columns"])): fk["options"].get("ondelete")
        for table in ("applications", "resumes")
        for fk in inspector.get_foreign_keys(table)
    }
    assert on_delete[("resumes", ("resume_id",))] == "SET NULL"
    assert on_delete[("application_attempts", ("source_attempt_id",))] == "SET NULL"
    connection.close()


def test_downgrade_leaves_no_trace_even_with_a_cv_that_has_no_file():
    connection = _connect()
    _bind(connection)
    MIGRATION.upgrade()
    connection.execute(
        sa.text(
            "INSERT INTO resumes (id, filename, file_bytes) "
            "VALUES ('33333333333333333333333333333333', 'b.docx', NULL)"
        )
    )

    MIGRATION.downgrade()

    resumes = _columns(connection, "resumes")
    assert "source_attempt_id" not in resumes
    assert resumes["file_bytes"]["nullable"] is False
    assert "resume_id" not in _columns(connection, "applications")
    assert "ix_applications_resume_id" not in _indexes(connection, "applications")
    assert "ix_resumes_source_attempt_id" not in _indexes(connection, "resumes")
    rows = dict(connection.execute(sa.text("SELECT filename, file_bytes FROM resumes")).all())
    assert rows == {"a.docx": b"\x01\x02", "b.docx": b""}
    connection.close()
