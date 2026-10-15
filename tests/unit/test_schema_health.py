"""Schema drift must be detectable without reading a traceback (2026-09-20).

The image shipped at `0004` against a database at `0003` and every page behind the
login returned 500 for a full deploy cycle, while `/health` kept reporting `ok`: it
only ever checked that the environment variable was present. `/health/schema` reads
the two revision strings the incident was about.
"""

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from src.db import ALEMBIC_CONFIG, code_head_revision


def revision_behind_head() -> str:
    """The parent of the head revision, derived so a new migration cannot stale it."""
    directory = ScriptDirectory.from_config(Config(str(ALEMBIC_CONFIG)))
    head = directory.get_current_head()
    behind = directory.get_revision(head).down_revision
    assert isinstance(behind, str), "the head must have a parent for this test to mean anything"
    return behind


def stamp(session, revision: str) -> None:
    """Put the database at one revision, the way `alembic stamp` would."""
    session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    session.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:rev)"), {"rev": revision}
    )
    session.commit()


def test_the_code_knows_the_revision_it_ships():
    assert code_head_revision() == "0018", "read from migrations/, not hand-maintained"


def test_a_database_one_revision_behind_head_is_a_503_with_both_revisions(client, session):
    head = code_head_revision()
    behind = revision_behind_head()
    stamp(session, behind)

    response = client.get("/health/schema")

    assert response.status_code == 503
    assert response.json() == {"database": behind, "code": head, "match": False}


def test_a_database_at_head_is_a_200(client, session):
    head = code_head_revision()
    stamp(session, head)

    response = client.get("/health/schema")

    assert response.status_code == 200
    assert response.json() == {"database": head, "code": head, "match": True}


def test_an_unstamped_database_says_so_rather_than_failing(client, session):
    session.execute(text("DROP TABLE IF EXISTS alembic_version"))
    session.commit()

    response = client.get("/health/schema")

    assert response.status_code == 503
    assert response.json()["database"] is None
    assert response.json()["match"] is False


def test_the_schema_endpoint_exposes_nothing_but_the_two_revisions(client, session):
    stamp(session, revision_behind_head())

    payload = client.get("/health/schema").json()

    assert set(payload) == {"database", "code", "match"}
    assert "postgres" not in str(payload) and "@" not in str(payload), "no connection string"


def test_a_mismatch_does_not_touch_the_liveness_endpoint(client, session):
    """`/health` stays what Cloud Run probes: no database, no cap, no drift report."""
    stamp(session, revision_behind_head())

    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/health/schema").status_code == 503