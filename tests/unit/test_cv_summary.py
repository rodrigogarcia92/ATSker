"""Proponer resumen on an analysed CV (PRD F7.3 rule 3 amended, F11.9).

The base is the CV's own summary first, then the F7.3 chain; the bullets and grades are the
CV's as the analysis read them (temporary ids included). Accepting still writes the pool and,
if ticked, the track — but it is checked against the CV's sources, so a citation of the CV's
own summary or of one of its bullets is accepted. The prompt is unchanged.
"""

import json

import pytest

from src.extract import client as extract_client
from src.extract.prompts import SUMMARY_V5
from src.generate.proposals import cv_summary_material
from src.models import Summary
from src.summaries import create_summary
from src.tracks import set_track_summary
from tests.conftest import login
from tests.unit.cv_support import draft_dict, make_cv
from tests.unit.test_generation import stored_application
from tests.unit.test_summary_v4 import GOOD, Queue

CV_SUMMARY = "Analista de datos con más de ocho años y machine learning."
TEMP_ID = "tmp-cv-1"
TEMP_TEXT = "Automaticé el reporte con Python"


def cv_application(session, career, *, summary: str | None = CV_SUMMARY):
    """An analysis of a CV whose one bullet is not in the master (a temporary id)."""
    cv = make_cv(
        session,
        career.first_profile,
        career.first_track,
        name="cv.docx",
        draft=draft_dict(TEMP_TEXT, summary=summary, skills=("machine learning",)),
    )
    application = stored_application(
        session,
        career,
        grades=[
            {
                "requirement": "python",
                "must_have": True,
                "level": 3,
                "basis": "direct",
                "bullet_id": TEMP_ID,
                "bullet_text": TEMP_TEXT,
            }
        ],
    )
    application.resume_id = cv.id
    application.report = {
        **application.report,
        "cv": {"resume_id": str(cv.id), "filename": "cv.docx", "chosen": "explicit"},
        "bullets": [{"id": TEMP_ID, "temporary": True, "role_id": "r", "text": TEMP_TEXT}],
    }
    session.commit()
    return application, cv


@pytest.fixture
def queue(monkeypatch, test_settings, career):
    def make(*texts, cites):
        stub = Queue(*texts, cites=cites)
        monkeypatch.setattr(extract_client, "_post", stub)
        return stub

    return make


def generate(client, application):
    return client.post(f"/applications/{application.id}/summary/generate", data={"dialog": "1"})


def test_the_material_is_the_cvs(session, career):
    application, cv = cv_application(session, career)

    material = cv_summary_material(career.first_profile.id, session, application)

    assert material.base.text == CV_SUMMARY
    assert material.base.origin == "file" and material.base.summary_id == f"cv-{cv.id}"
    assert material.bullets == [(TEMP_ID, TEMP_TEXT)], "the CV's bullets, not the track's"
    assert material.grades == [{"level": 3, "evidence_id": TEMP_ID}]
    assert "machine learning" not in material.pool, "a skill only the CV names is not confirmed"
    assert material.title == "Analista de datos" and material.language == "es"


def test_the_prompt_base_is_the_cvs_own_summary_and_its_cites_pass(
    client, session, career, queue
):
    application, cv = cv_application(session, career)
    stub = queue(GOOD, cites=[TEMP_ID, f"summary:cv-{cv.id}"])
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(stub.calls) == 1
    assert f"summary:cv-{cv.id}" in stub.user() and "ocho años" in stub.user()
    assert TEMP_TEXT in stub.user(), "the CV's bullet is what the model may cite"
    assert str(career.first_bullet.id) not in stub.user(), "the track's selection is not sent"
    assert "no pasa la validación" not in page


def test_a_cv_without_a_summary_falls_back_to_the_tracks(client, session, career, queue):
    pid = career.first_profile.id
    base = create_summary(pid, session, text="Analista con base de línea.", lang="es")
    set_track_summary(pid, session, career.first_track.id, lang="es", summary_id=base.id)
    application, _cv = cv_application(session, career, summary=None)
    stub = queue(GOOD, cites=[TEMP_ID, f"summary:{base.id}"])
    login(client, career.first.email)

    page = generate(client, application).text

    assert f"summary:{base.id}" in stub.user()
    assert "Basado en el resumen de tu línea" in page


def test_accepting_checks_the_cvs_sources_and_writes_the_pool(client, session, career):
    """Unchanged in effect — a pool row, the track only if ticked — but valid on CV cites."""
    application, cv = cv_application(session, career)
    login(client, career.first.email)
    payload = json.dumps(
        {"summary": {"text": GOOD, "cites": [TEMP_ID, f"summary:cv-{cv.id}"]}}
    )

    response = client.post(
        f"/applications/{application.id}/summary/accept",
        data={"payload": payload, "dialog": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303 and "summary_saved=1" in response.headers["location"]
    saved = session.query(Summary).filter(Summary.text == GOOD).one()
    assert saved.lang == "es"
    assert career.first_track.summary_es_id != saved.id, "the track only when ticked"


UNCONFIRMED = "Analista de datos con Python y machine learning."


def test_a_skill_outside_the_pool_is_refused_on_propose_and_on_accept(
    client, session, career, queue
):
    """A CV saved from an attempt never went through the merge review (M1)."""
    application, cv = cv_application(session, career)
    stub = queue(UNCONFIRMED, cites=[TEMP_ID, f"summary:cv-{cv.id}"])
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(stub.calls) >= 1
    assert "Habilidades que no están en tus datos" in page and "«machine learning»" in page

    payload = json.dumps(
        {"summary": {"text": UNCONFIRMED, "cites": [TEMP_ID, f"summary:cv-{cv.id}"]}}
    )
    response = client.post(
        f"/applications/{application.id}/summary/accept",
        data={"payload": payload, "dialog": "1"},
    )
    assert response.status_code == 200 and "no pasa la validación" in response.text
    assert session.query(Summary).filter(Summary.text == UNCONFIRMED).count() == 0


def test_a_cite_outside_the_cvs_sources_is_still_refused(client, session, career):
    application, _cv = cv_application(session, career)
    login(client, career.first.email)
    payload = json.dumps({"summary": {"text": GOOD, "cites": ["not-in-the-cv"]}})

    response = client.post(
        f"/applications/{application.id}/summary/accept",
        data={"payload": payload, "dialog": "1"},
    )

    assert response.status_code == 200 and "no pasa la validación" in response.text
    assert session.query(Summary).filter(Summary.text == GOOD).count() == 0


def test_a_deleted_cv_still_proposes_from_the_report(client, session, career, queue):
    application, cv = cv_application(session, career)
    application.resume_id = None
    session.delete(cv)
    session.commit()
    stub = queue(GOOD, cites=[TEMP_ID])
    login(client, career.first.email)

    page = generate(client, application).text

    assert len(stub.calls) == 1 and TEMP_TEXT in stub.user()
    assert "no pasa la validación" not in page


def test_the_prompt_version_is_unchanged():
    assert SUMMARY_V5.version == "summary_v5"
