"""Shared test setup.

The suite runs offline against SQLite: the deterministic core is the part that must
be testable without a network, and the database-backed routes get the same
treatment by overriding `get_db`. PostgreSQL-specific behaviour (migrations,
pgvector) is exercised against the Neon dev branch, not here.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth.accounts import create_account
from src.bullets import create_bullet
from src.config import get_settings
from src.letters import create_letter
from src.models import Base, Profile, Skill, User
from src.roles import create_role
from src.stories import create_story, set_linked_bullets
from src.summaries import create_summary
from src.tracks import create_track, set_track_bullets
from src.web.deps import get_db
from src.web.main import create_app

PASSWORD = "correct horse battery staple"  # noqa: S105 - synthetic fixture password
TEST_MODEL = "test/model-v1"


@pytest.fixture
def test_settings(monkeypatch):
    """Values a developer's .env would otherwise supply; no real credentials."""
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("OPENROUTER_MODEL", TEST_MODEL)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-api-key")
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


@pytest.fixture
def vocabulary(session) -> None:
    """Two canonical skills with Spanish aliases, one of them multi-word."""
    session.add_all(
        [
            Skill(
                canonical="python",
                aliases=["python", "py"],
                lang_tags=["es", "en"],
            ),
            Skill(
                canonical="machine learning",
                aliases=[
                    "machine learning",
                    "aprendizaje automático",
                    "aprendizaje automatico",
                    "learning",
                    "ml",
                ],
                lang_tags=["es", "en"],
            ),
        ]
    )
    session.commit()


@pytest.fixture
def career(session, two_accounts, vocabulary) -> SimpleNamespace:
    """One role, bullet and story for each account, so isolation can be tested."""
    (first, first_profile), (second, second_profile) = two_accounts

    first_role = create_role(first_profile.id, session, employer="Acme", title="Analista de datos")
    second_role = create_role(second_profile.id, session, employer="Globex", title="Ingeniera")
    first_bullet = create_bullet(
        first_profile.id,
        session,
        role_id=first_role.id,
        text_es="Reduje 30% el tiempo de reporte con Python",
        text_en=None,
        chips=["python", "cobalto"],
    )
    second_bullet = create_bullet(
        second_profile.id,
        session,
        role_id=second_role.id,
        text_es="Modelo de riesgo en producción",
        text_en=None,
        chips=["machine learning"],
    )
    first_story = create_story(
        first_profile.id,
        session,
        title="Migración del reporte",
        body="Llevé el reporte manual a un proceso automático.",
        role_id=first_role.id,
        tags=["migracion"],
    )
    set_linked_bullets(first_profile.id, session, first_story.id, [first_bullet.id])
    second_story = create_story(
        second_profile.id,
        session,
        title="Modelo de riesgo",
        body="Puse un modelo en producción con monitoreo.",
        tags=[],
    )
    first_letter = create_letter(
        first_profile.id,
        session,
        name="Datos",
        applies_when="Para puestos de analista de datos",
        presentation="Me presento.",
        achievements="Logros.",
    )
    second_letter = create_letter(
        second_profile.id,
        session,
        name="Riesgo",
        applies_when="Para puestos de riesgo",
        presentation="Me presento.",
        achievements="Logros.",
    )
    first_track = create_track(
        first_profile.id,
        session,
        name="Analista de datos",
        applies_when="Puestos de analista de datos",
        lang="es",
        headline="Analista de datos",
    )
    second_track = create_track(
        second_profile.id,
        session,
        name="Riesgo",
        applies_when="Puestos de riesgo",
        lang="es",
    )
    set_track_bullets(first_profile.id, session, first_track.id, [first_bullet.id])
    set_track_bullets(second_profile.id, session, second_track.id, [second_bullet.id])
    first_summary = create_summary(
        first_profile.id,
        session,
        text="Cinco años automatizando reportes para dirección.",
        lang="es",
    )
    second_summary = create_summary(
        second_profile.id,
        session,
        text="Modelos de riesgo en producción.",
        lang="es",
    )
    session.commit()
    return SimpleNamespace(
        first=first,
        first_profile=first_profile,
        second=second,
        second_profile=second_profile,
        first_role=first_role,
        second_role=second_role,
        first_bullet=first_bullet,
        second_bullet=second_bullet,
        first_story=first_story,
        second_story=second_story,
        first_letter=first_letter,
        second_letter=second_letter,
        first_track=first_track,
        second_track=second_track,
        first_summary=first_summary,
        second_summary=second_summary,
    )


def login(client: TestClient, email: str, password: str = PASSWORD):
    return client.post("/login", data={"email": email, "password": password})
