"""Attempt scoring and the downstream checks (PRD F10.3 steps 5-6, A4, B.3).

The ephemeral track is scored through the analysis path, so an unchanged export makes
no grading call (the content-hash cache answers with the analysis's own grades) and a
changed one makes exactly one. A keyword the user holds but the track did not show
raises Keywords; a file in the other language raises the F4.2 alert and is still
scored; and the advice reads for the document.
"""

import pytest

from src.bullets import create_bullet
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from src.web.alerts import advice_line
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


def _attempt(session) -> ApplicationAttempt:
    return session.query(ApplicationAttempt).order_by(ApplicationAttempt.attempt_no.desc()).first()


def test_an_unchanged_export_makes_no_grading_call_and_scores_the_analysis(
    client, session, career, provider
):
    """A4: the same grading input, so the cache answers and the score is identical."""
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    before = len(provider.calls_for("EvidenceGrading"))

    response = upload(
        client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es)
    )

    assert response.status_code == 200
    assert len(provider.calls_for("EvidenceGrading")) == before, "served from the cache"
    attempt = _attempt(session)
    assert attempt.status == "done"
    assert attempt.report["score"] == analysis.report["score"]
    assert attempt.report["llm"]["kind"] == "attempt", "its wall time is its own (F12.4)"


def test_an_attempt_reuses_the_stored_queries_and_derives_nothing(
    client, session, career, provider
):
    """F10.3/F12.2: the report carries the trees; the derivation was already paid for."""
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    before = len(provider.calls_for("BooleanQuerySet"))

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    assert len(provider.calls_for("BooleanQuerySet")) == before, "no derivation call"
    attempt = _attempt(session)
    assert [row["query_text"] for row in attempt.report["recall"]["queries"]] == [
        row["query_text"] for row in analysis.report["recall"]["queries"]
    ]


def test_one_changed_bullet_makes_one_grading_call(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    changed = f"{career.first_bullet.text_es} y SQL"
    provider.answers["ResumeExtraction"] = resume_payload(changed)
    # The changed bullet gets a temporary id, so no master id may be cited.
    provider.answers["EvidenceGrading"] = grading_payload(None)
    before = len(provider.calls_for("EvidenceGrading"))

    upload(client, application.id, docx_bytes("Experiencia", changed))

    assert len(provider.calls_for("EvidenceGrading")) - before == 1
    attempt = _attempt(session)
    assert attempt.report["bullets"][0]["temporary"] is True


def test_a_held_keyword_raises_keywords_towards_the_ceiling(client, session, career, provider):
    """F10.10 criterion 2: the file says what the user holds and the track did not."""
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
    application, analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, extra.text_es
    )

    upload(
        client,
        application.id,
        docx_bytes("Experiencia", career.first_bullet.text_es, extra.text_es),
    )

    attempt = _attempt(session)
    before = analysis.report["score"]["sub_scores"]["keywords"]["value"]
    after = attempt.report["score"]["sub_scores"]["keywords"]["value"]
    ceiling = attempt.report["ceiling"]["sub_scores"]["keywords"]["ceiling"]
    assert after > before, "the keyword the user holds raises Keywords"
    assert after <= ceiling, "and the keyword ceiling bounds it"


def test_a_file_in_the_other_language_raises_the_alert_and_is_scored(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        "Built a churn model with Python", language="en"
    )
    # The file's bullet is new, so no master id may be cited.
    provider.answers["EvidenceGrading"] = grading_payload(None)

    upload(client, application.id, docx_bytes("Experience", "Built a churn model with Python"))

    attempt = _attempt(session)
    assert attempt.status == "done", "it is still scored"
    alerts = attempt.report["gaps"]["alerts"]
    assert any(alert.get("kind") == "language_mismatch" for alert in alerts)


def test_the_advice_reads_for_the_document():
    item = {"kind": "add_bullet", "values": {"canonical": "python"}}

    assert "tu documento" in advice_line(item, "es", for_file=True)
    assert "a la línea" in advice_line(item, "es"), "the analysis wording is unchanged"
