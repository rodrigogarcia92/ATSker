"""The new-in-this-document flags and the change list (PRD F10.5, F10.4 step 4, B.4).

The file was edited outside ATSker, so the F7.3 extractors are pointed at it: a skill
the pool does not hold and a number no stored row supports are flagged, the flag
survives "Descartar", and the change list names what moved against the previous
attempt.
"""

import pytest

from src.attempt_flags import discard_attempt
from src.bullets import create_bullet
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    grading_payload,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def upload(client, application_id, data, name: str = "cv.docx"):
    return client.post(
        f"/applications/{application_id}/attempts",
        files={"file": (name, data, DOCX_TYPE)},
        follow_redirects=False,
    )


def _attempts(session):
    return (
        session.query(ApplicationAttempt)
        .order_by(ApplicationAttempt.attempt_no)
        .all()
    )


def test_a_skill_the_pool_does_not_hold_is_flagged_and_survives_discard(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, skills=("machine learning",)
    )

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    attempt = _attempts(session)[0]
    assert "machine learning" in attempt.report["flags"]["skills"]
    assert attempt.report["flags"]["above_ceiling"] is False

    discard_attempt(attempt)
    session.commit()

    fresh = _attempts(session)[0]
    assert fresh.report["draft"] is None
    assert "machine learning" in fresh.report["flags"]["skills"], "the flag stays"


def test_an_invented_number_is_flagged(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    invented = f"{career.first_bullet.text_es} y mejoré el cierre un 37%"
    provider.answers["ResumeExtraction"] = resume_payload(invented)
    provider.answers["EvidenceGrading"] = grading_payload(None)

    upload(client, application.id, docx_bytes("Experiencia", invented))

    attempt = _attempts(session)[0]
    assert "37%" in attempt.report["flags"]["claims"]


def test_the_change_list_names_the_search_the_document_now_passes(
    client, session, career, provider
):
    """A bullet the file adds brings `machine learning`, so the strict search passes."""
    extra = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Entrené un modelo de machine learning en producción",
        text_en=None,
        chips=[],
    )
    session.commit()
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, extra.text_es
    )
    upload(
        client,
        application.id,
        docx_bytes("Experiencia", career.first_bullet.text_es, extra.text_es),
    )

    first, second = _attempts(session)
    assert first.report["change"] == {}, "there was nothing before the first attempt"
    assert second.report["change"]["searches_found"] == ["strict"]
