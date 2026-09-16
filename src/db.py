"""Database engine and session factory.

`NullPool` is not a tuning accident: Neon's free tier bills compute-hours, and a
pool that keeps a connection open also keeps the database awake. Every request
opens a connection, uses it, and returns it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.config import get_settings

# Neon hands out `postgresql://…` and only psycopg 3 is installed, so the bare
# scheme would resolve to psycopg2 and fail at engine creation. Schemes are
# case-insensitive (RFC 3986), and whitespace in a connection string is always a
# paste accident — build steps E6 warns about exactly that trailing newline.
_DRIVERS = {
    "postgres": "postgresql+psycopg",
    "postgresql": "postgresql+psycopg",
    "postgresql+psycopg": "postgresql+psycopg",
    "sqlite": "sqlite",
}


def normalized_url(raw: str) -> str:
    """Pick the installed driver for a known scheme; leave anything else alone.

    A scheme that is not recognised is not repaired — a corrupt secret must fail
    loudly rather than be guessed at.
    """
    url = raw.strip()
    scheme, separator, remainder = url.partition("://")
    if separator and scheme.lower() in _DRIVERS:
        return f"{_DRIVERS[scheme.lower()]}://{remainder}"
    return url


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    raw = normalized_url(settings.database_url.get_secret_value())
    try:
        return create_engine(raw, poolclass=NullPool)
    except (NoSuchModuleError, ImportError) as exc:
        # SQLAlchemy's own message ("Can't load plugin: sqlalchemy.dialects:Ppostgresql")
        # says nothing about where to look; a corrupt secret is the usual cause and the
        # scheme is the tell. Loud, but actionable.
        raise RuntimeError(
            f"DATABASE_URL scheme {raw.partition('://')[0]!r} cannot be loaded. "
            "A stray character in the stored secret is the usual cause."
        ) from exc


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    # expire_on_commit=False: templates render after a commit, and re-fetching
    # every attribute would be another round trip to a database billed by time.
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def new_session() -> Session:
    return _session_factory()()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Session for non-web callers (scripts); commits on success, rolls back on error."""
    with new_session() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
