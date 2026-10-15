"""The attempt upload over HTTP (PRD F10.3, B.1): the file lifecycle and the limit.

The provider is stubbed at `client._post`. What is asserted is A5/A6: the SHA-256 is
the only trace of the file, no bytes reach the row, the report or the disk; an empty
extraction fails plainly and does not count towards the limit; another profile's
analysis is not found; and the eleventh attempt is refused with a stated reason.
"""

import hashlib
import os
import tempfile
import uuid
from decimal import Decimal

import pytest

from src.applications import create_application
from src.attempts import counted_attempts
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_ingest_routes import DOCX_TYPE, EMPTY, Provider, docx_bytes, long_cv, plain


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _application(profile_id, session):
    """A bare row for the cases that never reach the pipeline."""
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


def upload(client, application_id, data, name: str = "cv.docx"):
    return client.post(
        f"/applications/{application_id}/attempts",
        files={"file": (name, data, DOCX_TYPE)},
        follow_redirects=False,
    )


def test_an_attempt_stores_its_sha_and_keeps_no_bytes(
    client, session, career, provider, monkeypatch, tmp_path
):
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    data = docx_bytes("Experiencia", career.first_bullet.text_es)
    # An isolated temp directory: nothing else on the machine can write into it.
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    before = set(os.listdir(tempfile.gettempdir()))

    response = upload(client, application.id, data)

    assert response.status_code == 200
    attempt = session.query(ApplicationAttempt).one()
    assert attempt.status == "done"
    assert attempt.attempt_no == 1
    assert attempt.file_format == "docx"
    assert attempt.file_sha256 == hashlib.sha256(data).hexdigest()
    assert attempt.lang == "es"
    # A5: the report carries the draft, the file's bullets and the score — never bytes.
    assert isinstance(attempt.report["draft"], dict)
    assert attempt.report["bullets"][0]["text"] == career.first_bullet.text_es
    assert "file_bytes" not in attempt.report
    assert attempt.report["score"]["capped"] == analysis.report["score"]["capped"]
    assert set(os.listdir(tempfile.gettempdir())) == before, "nothing was written to disk"


def test_an_empty_extraction_fails_and_is_not_counted(client, session, career, monkeypatch):
    monkeypatch.setattr(extract_client, "_post", Provider(EMPTY))
    login(client, career.first.email)
    application = _application(career.first_profile.id, session)

    response = upload(client, application.id, long_cv())

    assert response.status_code == 200
    attempt = session.query(ApplicationAttempt).one()
    assert attempt.status == "failed"
    assert "caracteres y no volvió nada" in plain(response.text)
    assert counted_attempts(career.first_profile.id, session, application.id) == 0


def test_a_post_for_another_users_application_is_404(client, session, career, provider):
    login(client, career.first.email)
    theirs = _application(career.second_profile.id, session)

    response = upload(client, theirs.id, docx_bytes("Experiencia", "Reduje el cierre"))

    assert response.status_code == 404
    assert session.query(ApplicationAttempt).count() == 0


def test_the_eleventh_attempt_is_refused_with_a_stated_reason(client, session, career, provider):
    login(client, career.first.email)
    application = _application(career.first_profile.id, session)
    for number in range(1, 11):
        session.add(
            ApplicationAttempt(
                application_id=application.id,
                profile_id=career.first_profile.id,
                attempt_no=number,
                status="done",
                file_sha256="a" * 64,
                prompt_versions={},
            )
        )
    session.commit()

    response = upload(client, application.id, docx_bytes("Experiencia", "Reduje el cierre"))

    assert response.status_code == 409
    assert "10 intentos" in response.json()["detail"]
    assert session.query(ApplicationAttempt).count() == 10, "nothing was created"
