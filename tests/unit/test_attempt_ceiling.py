"""An attempt shows the analysis's ceiling, never one computed from the file (PRD F10.2, F10.3, E2).

The ceiling is what the user's *material* allows, so a worse file cannot lower it and a
richer one cannot raise it. It changes only when the master data does, and then it is the
same recomputed value the analysis's own page shows.
"""

import json
import re

import pytest

from src.analysis import ceiling_for_report
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    grading_payload,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes, plain

NEW_BULLET = "Entrené un modelo de machine learning en producción"


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def upload(client, application_id, text: str):
    return client.post(
        f"/applications/{application_id}/attempts",
        files={"file": ("cv.docx", docx_bytes("Experiencia", text), DOCX_TYPE)},
        follow_redirects=False,
    )


def _attempts(session) -> list[ApplicationAttempt]:
    session.expire_all()
    return session.query(ApplicationAttempt).order_by(ApplicationAttempt.attempt_no).all()


def _page_ceiling(client, application_id) -> int:
    page = plain(client.get(f"/applications/{application_id}").text)
    return int(re.search(r"Techo con tu material: (\d+)", page).group(1))


def _stored(value):
    return json.loads(json.dumps(value))


def test_a_worse_file_keeps_the_analysis_ceiling(client, session, career, provider):
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    upload(client, application.id, career.first_bullet.text_es)
    # The second file's bullet is new and graded lower than the master one was.
    provider.answers["ResumeExtraction"] = resume_payload("Hice reportes varios")
    provider.answers["EvidenceGrading"] = grading_payload(None)
    upload(client, application.id, "Hice reportes varios")

    first, second = _attempts(session)

    assert second.job_match < first.job_match, "the file really is worse"
    assert (first.ceiling_low, first.ceiling_high) == (second.ceiling_low, second.ceiling_high)
    assert second.report["ceiling"] == _stored(analysis.report["ceiling"])
    assert second.ceiling_high == _page_ceiling(client, application.id)


def test_a_master_change_between_attempts_gives_the_recomputed_ceiling(
    client, session, career, provider
):
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    upload(client, application.id, career.first_bullet.text_es)
    career.first_bullet.skills = [*career.first_bullet.skills, "sql"]
    session.commit()

    upload(client, application.id, career.first_bullet.text_es)

    first, second = _attempts(session)
    session.refresh(application)
    recomputed = ceiling_for_report(
        career.first_profile.id, session, report=application.report, track=career.first_track
    )
    assert recomputed["fingerprint"] != analysis.report["ceiling"]["fingerprint"]
    assert first.report["ceiling"]["fingerprint"] == analysis.report["ceiling"]["fingerprint"]
    assert second.report["ceiling"] == _stored(recomputed)
    assert second.ceiling_high == _page_ceiling(client, application.id)
    page = plain(client.get(f"/applications/{application.id}").text)
    assert "recalculado con tu material actual" in page


def test_a_sub_score_above_its_ceiling_is_shown_as_it_is(client, session, career, provider):
    """The file claims a keyword the material does not hold: no clamp, and the F10.5 note
    follows the analysis's high end."""
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(NEW_BULLET)
    provider.answers["EvidenceGrading"] = grading_payload(None)
    upload(client, application.id, NEW_BULLET)

    (attempt,) = _attempts(session)

    keywords = attempt.report["score"]["sub_scores"]["keywords"]["value"]
    ceiling = attempt.report["ceiling"]["sub_scores"]["keywords"]["ceiling"]
    assert keywords > ceiling, "the file claims more than the material holds"
    modal = plain(
        client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    )
    assert f"{round(keywords * 100)} / {round(ceiling * 100)}" in modal
    high = analysis.report["ceiling"]["high"]
    assert attempt.report["flags"]["above_ceiling"] is (attempt.job_match > high)
