"""Connection-string handling.

This exists because production broke here once: `postgresql://` (what neonctl
prints) resolved to psycopg2, which the image does not contain, and every
database-touching request returned 500.
"""

import pytest

from src.config import get_settings
from src.db import get_engine, normalized_url

BASE = "neon-owner:secret@ep-example-1234-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require"


def test_bare_postgresql_scheme_selects_the_installed_driver():
    assert normalized_url(f"postgresql://{BASE}") == f"postgresql+psycopg://{BASE}"
    assert normalized_url(f"postgres://{BASE}") == f"postgresql+psycopg://{BASE}"
    assert normalized_url(f"postgresql+psycopg://{BASE}") == f"postgresql+psycopg://{BASE}"


def test_scheme_case_is_not_significant():
    assert normalized_url(f"PostgreSQL://{BASE}") == f"postgresql+psycopg://{BASE}"


def test_surrounding_whitespace_is_removed():
    assert normalized_url(f"\n postgresql://{BASE}\n") == f"postgresql+psycopg://{BASE}"


def test_a_corrupt_scheme_is_not_repaired():
    """A stray character means the secret is wrong; guessing would hide it."""
    assert normalized_url(f"Ppostgresql://{BASE}") == f"Ppostgresql://{BASE}"


def test_sqlite_is_left_as_is():
    assert normalized_url("sqlite:///fixtures/smoke.db") == "sqlite:///fixtures/smoke.db"


def test_engine_reports_an_unloadable_scheme_by_name(monkeypatch):
    """The production failure this guards: an opaque dialect error, no direction."""
    monkeypatch.setenv("DATABASE_URL", f"Ppostgresql://{BASE}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="Ppostgresql"):
            get_engine()
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
