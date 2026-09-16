"""Database engine and session factory.

`NullPool` is not a tuning accident: Neon's free tier bills compute-hours, and a
pool that keeps a connection open also keeps the database awake. Every request
opens a connection, uses it, and returns it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from src.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL is not set")
    return create_engine(settings.database_url.get_secret_value(), poolclass=NullPool)


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
