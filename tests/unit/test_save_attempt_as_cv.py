"""Saving an attempt as the track's CV (PRD F10.7, F11.7).

"Subir a esta línea" turns a finished attempt into a CV of the application's track: its
draft, its readability findings, the file's SHA-256 — and no bytes. It is the track's newest
CV, merges no material, is idempotent, and "Analizar con este CV" then scores the same
posting on it exactly as the attempt did, with no new grading call (F11.11 criterion 4).
"""

import pytest

from src.bullets import list_bullets
from src.extract import client as extract_client
from src.models import Application, ApplicationAttempt, Resume
from src.resumes import latest_cv
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.cv_support import make_cv
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes

NEW_TEXT = "Automaticé el cierre mensual con scripts propios"


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def upload(client, application, *texts):
    return client.post(
        f"/applications/{application.id}/attempts",
        files={"file": ("cv.docx", docx_bytes("Experiencia", *texts), DOCX_TYPE)},
        follow_redirects=False,
    )


def attempt_of(session) -> ApplicationAttempt:
    return session.query(ApplicationAttempt).order_by(ApplicationAttempt.attempt_no.desc()).first()


def save_url(application, attempt) -> str:
    return f"/applications/{application.id}/attempts/{attempt.id}/save-cv"


def analysed_attempt(client, session, career, provider, *, with_new_bullet=False):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    texts = [career.first_bullet.text_es]
    if with_new_bullet:
        texts.append(NEW_TEXT)
        provider.answers["ResumeExtraction"] = resume_payload(*texts)
    upload(client, application, *texts)
    return application, attempt_of(session)


def test_the_attempt_becomes_the_tracks_newest_cv_without_bytes(
    client, session, career, provider
):
    application, attempt = analysed_attempt(client, session, career, provider)

    response = client.post(save_url(application, attempt))

    assert response.status_code == 200
    resume = session.query(Resume).filter(Resume.source_attempt_id == attempt.id).one()
    assert resume.track_id == application.track_id
    assert resume.profile_id == career.first_profile.id
    assert resume.draft == attempt.report["draft"]
    assert resume.gate == attempt.report["gate"]
    assert resume.sha256 == attempt.file_sha256
    assert resume.file_bytes is None, "attempts never store a file"
    assert resume.merged_at is not None and resume.active
    assert "Intento 1" in resume.filename and resume.filename.endswith(".docx")
    assert latest_cv(career.first_profile.id, session, application.track_id).id == resume.id


def test_the_confirmation_offers_the_two_next_steps_and_says_the_file_was_not_kept(
    client, session, career, provider
):
    application, attempt = analysed_attempt(client, session, career, provider)

    page = client.post(save_url(application, attempt)).text

    assert "CV guardado en la línea" in page and "Analista de datos" in page
    assert "Incorporar también su contenido a mi material" in page
    assert f"/applications/{application.id}/attempts/{attempt.id}/incorporate" in page
    assert "Analizar con este CV" in page
    assert f'action="/applications/{application.id}/reanalyze"' in page
    assert "El archivo no se conservó" in page


def test_saving_merges_nothing_into_the_material(client, session, career, provider):
    application, attempt = analysed_attempt(
        client, session, career, provider, with_new_bullet=True
    )
    before = {bullet.id for bullet in list_bullets(career.first_profile.id, session)}

    client.post(save_url(application, attempt))

    after = {bullet.id for bullet in list_bullets(career.first_profile.id, session)}
    assert after == before, "the F2.5 review is the only way into the master data"


def test_pressing_it_again_shows_the_cv_already_saved(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)

    first = client.post(save_url(application, attempt)).text
    second = client.post(save_url(application, attempt)).text

    assert session.query(Resume).filter(Resume.source_attempt_id == attempt.id).count() == 1
    assert "es ahora un CV de la línea" in first
    assert "ya estaba guardado como CV de la línea" in second


def test_analysing_with_the_saved_cv_scores_exactly_as_the_attempt_with_no_grading_call(
    client, session, career, provider
):
    """F11.11 criterion 4 — with a bullet the master does not have, so the ids matter."""
    application, attempt = analysed_attempt(
        client, session, career, provider, with_new_bullet=True
    )
    assert attempt.report["bullets"][1]["temporary"] is True
    client.post(save_url(application, attempt))
    resume = session.query(Resume).filter(Resume.source_attempt_id == attempt.id).one()
    grading_before = len(provider.calls_for("EvidenceGrading"))
    extraction_before = len(provider.calls_for("ResumeExtraction"))

    response = client.post(
        f"/applications/{application.id}/reanalyze",
        data={"resume_id": str(resume.id)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert len(provider.calls_for("EvidenceGrading")) == grading_before, "zero grading calls"
    assert len(provider.calls_for("ResumeExtraction")) == extraction_before
    created = session.query(Application).filter(Application.resume_id == resume.id).one()
    assert created.id != application.id
    assert created.jd_hash == application.jd_hash, "the same posting"
    assert created.report["score"] == attempt.report["score"], "exactly the attempt's score"
    assert created.report["cv"]["chosen"] == "explicit"
    assert [row["text"] for row in created.report["bullets"]] == [
        row["text"] for row in attempt.report["bullets"]
    ]


def test_an_unchanged_attempt_also_scores_the_same(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)
    client.post(save_url(application, attempt))
    resume = session.query(Resume).filter(Resume.source_attempt_id == attempt.id).one()
    grading_before = len(provider.calls_for("EvidenceGrading"))

    client.post(
        f"/applications/{application.id}/reanalyze", data={"resume_id": str(resume.id)}
    )

    assert len(provider.calls_for("EvidenceGrading")) == grading_before
    created = session.query(Application).filter(Application.resume_id == resume.id).one()
    assert created.report["score"] == attempt.report["score"]


def test_another_profiles_attempt_is_a_404(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)
    client.post("/logout")
    login(client, career.second.email)

    response = client.post(save_url(application, attempt))

    assert response.status_code == 404
    assert session.query(Resume).filter(Resume.source_attempt_id == attempt.id).count() == 0


def test_an_attempt_of_another_application_is_a_404(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)
    other, _analysis = analyzed_application(session, career, provider)

    response = client.post(save_url(other, attempt))

    assert response.status_code == 404


def test_a_discarded_attempt_is_not_offered_and_cannot_be_saved(
    client, session, career, provider
):
    application, attempt = analysed_attempt(client, session, career, provider)
    client.post(f"/applications/{application.id}/attempts/{attempt.id}/discard")
    session.refresh(attempt)

    status = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    forced = client.post(save_url(application, attempt))

    assert "save-cv" not in status
    assert forced.status_code == 409
    assert session.query(Resume).filter(Resume.source_attempt_id == attempt.id).count() == 0


def test_a_finished_attempt_offers_the_button_in_the_modal(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)

    status = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text

    assert save_url(application, attempt) in status
    assert "Subir a esta línea" in status


def test_a_failed_attempt_cannot_be_saved(client, session, career, provider):
    application, attempt = analysed_attempt(client, session, career, provider)
    attempt.status = "failed"
    session.commit()

    assert client.post(save_url(application, attempt)).status_code == 409


def test_the_reanalysis_of_a_foreign_resume_is_a_404(client, session, career, provider):
    application, _attempt = analysed_attempt(client, session, career, provider)
    theirs = make_cv(session, career.second_profile, career.second_track, name="theirs.docx")

    response = client.post(
        f"/applications/{application.id}/reanalyze", data={"resume_id": str(theirs.id)}
    )

    assert response.status_code == 404
    assert session.query(Application).count() == 1

