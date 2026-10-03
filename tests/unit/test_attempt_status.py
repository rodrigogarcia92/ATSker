"""The attempt status, discard and report routes (PRD F10.3, B.5).

Every route is owner-scoped (another profile's row is a 404), a `running` row older
than ten minutes reads as failed, "Descartar" blanks the draft and keeps the report,
and the report route renders the full F5 report through the analysis's own template.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.applications import create_application
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes, plain


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _application(profile_id, session):
    application = create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )
    session.commit()
    return application


def _attempt(profile_id, session, application, **overrides) -> ApplicationAttempt:
    values = {
        "application_id": application.id,
        "profile_id": profile_id,
        "attempt_no": 1,
        "file_sha256": "a" * 64,
        "file_format": "docx",
        "status": "running",
        "prompt_versions": {},
        "created_at": datetime.now(UTC),
    }
    values.update(overrides)
    row = ApplicationAttempt(**values)
    session.add(row)
    session.flush()
    return row


def upload(client, application_id, data, name: str = "cv.docx"):
    return client.post(
        f"/applications/{application_id}/attempts",
        files={"file": (name, data, DOCX_TYPE)},
        follow_redirects=False,
    )


def test_every_route_is_404_for_a_row_the_profile_does_not_own(client, session, career, provider):
    login(client, career.first.email)
    theirs = _application(career.second_profile.id, session)
    theirs_attempt = _attempt(career.second_profile.id, session, theirs)
    session.commit()

    base = f"/applications/{theirs.id}/attempts/{theirs_attempt.id}"
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/discard").status_code == 404
    assert client.get(f"{base}/report").status_code == 404
    assert client.get(f"/applications/{theirs.id}/attempts/{uuid.uuid4()}").status_code == 404


def test_an_attempt_id_from_another_application_is_404(client, session, career, provider):
    login(client, career.first.email)
    first = _application(career.first_profile.id, session)
    second = _application(career.first_profile.id, session)
    attempt = _attempt(career.first_profile.id, session, second)
    session.commit()

    assert client.get(f"/applications/{first.id}/attempts/{attempt.id}").status_code == 404


def test_a_stale_running_row_reads_as_failed(client, session, career, provider):
    login(client, career.first.email)
    application = _application(career.first_profile.id, session)
    attempt = _attempt(
        career.first_profile.id,
        session,
        application,
        created_at=datetime.now(UTC) - timedelta(minutes=11),
    )
    session.commit()

    page = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    assert "Fallido" in page, "a run nothing will ever finish reads as failed"


def test_discard_blanks_the_draft_and_keeps_the_flags(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, skills=("machine learning",)
    )
    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    attempt = session.query(ApplicationAttempt).one()
    assert attempt.report["draft"] is not None

    response = client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/discard"
    )

    assert response.status_code == 200
    session.expire_all()
    assert attempt.report["draft"] is None
    assert attempt.report["flags"]["skills"] == ["machine learning"]


def test_the_report_route_renders_the_full_report(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    attempt = session.query(ApplicationAttempt).one()

    page = plain(
        client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text
    )

    assert "Ajuste general" in page
    assert "Techo con tu material" in page
    assert "Componentes" in page
