"""Shared test setup.

The suite runs offline against SQLite: the deterministic core is the part that must
be testable without a network, and the database-backed routes get the same
treatment by overriding `get_db`. PostgreSQL-specific behaviour (migrations,
pgvector) is exercised against the Neon dev branch, not here.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth.accounts import create_account
from src.config import get_settings
from src.models import Base, Profile, User
from src.web.deps import get_db
from src.web.main import create_app

PASSWORD = "correct horse battery staple"  # noqa: S105 - synthetic fixture password


@pytest.fixture
def test_settings(monkeypatch):
    """A session secret that exists without a developer's .env file."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def session_factory():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def session(session_factory) -> Session:
    with session_factory() as db:
        yield db


@pytest.fixture
def client(session_factory, test_settings) -> TestClient:
    app = create_app()

    def override_get_db():
        with session_factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def two_accounts(session) -> tuple[tuple[User, Profile], tuple[User, Profile]]:
    first = create_account(session, "persona@example.com", PASSWORD, "Ana")
    second = create_account(session, "persona@example.com", PASSWORD, "Bea")
    session.commit()
    return first, second


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/login", data={"email": email, "password": password})
