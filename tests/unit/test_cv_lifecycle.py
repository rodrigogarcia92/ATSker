"""Old reports, history and deletion around a CV (PRD F11.8, F9, F2.8, F11.10).

A report stored before F11 keeps rendering and says what it scored; the history names the
CV of each analysis; deleting a CV leaves its analyses with the file's name, and the
confirmation says how many there are.
"""

import re
import uuid

import pytest

from src.analysis import analyze
from src.applications import create_application, list_applications
from src.deletion import delete_application, delete_resume, impact_resume
from src.extract import client as extract_client
from src.models import Application, ApplicationAttempt, Resume
from tests.conftest import login
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import analysis_form, draft_dict, make_cv


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def own(career) -> dict:
    return draft_dict(career.first_bullet.text_es)


def analyse(client, session, career, **fields):
    response = client.post(
        "/analyze",
        data=analysis_form(session, career, jd_text=POSTING, **fields),
        follow_redirects=False,
    )
    assert response.status_code == 303
    return session.get(Application, uuid.UUID(response.headers["location"].rsplit("/", 1)[1]))


def legacy_application(session, career) -> Application:
    """An analysis as the app stored it before F11: a track, no CV."""
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING, track=career.first_track)
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=POSTING,
        jd_hash=analysis.jd_hash,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    return application


# --- F11.8: reports stored before F11 ---------------------------------------------------------


def test_a_report_stored_before_f11_renders_unchanged_with_its_label(
    client, session, career, provider
):
    """F11.11 criterion 7."""
    application = legacy_application(session, career)
    stored = dict(application.report)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "Analizado sobre la línea (antes de elegir CV)" in page
    assert "CV analizado:" not in page and "CV eliminado" not in page
    assert application.resume_id is None
    session.refresh(application)
    assert application.report == stored, "never recomputed"
    assert "Requisitos y evidencia" in page and "Recomendaciones" in page
    assert "Con tu material" not in page, "no F11.5 note on a report that never had one"


def test_an_old_report_offers_to_analyse_on_a_cv_as_a_new_analysis(
    client, session, career, provider
):
    application = legacy_application(session, career)
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    response = client.post(
        f"/applications/{application.id}/reanalyze",
        data={"resume_id": str(cv.id)},
        follow_redirects=False,
    )

    assert f'action="/applications/{application.id}/reanalyze"' in page
    assert response.status_code == 303
    assert session.query(Application).count() == 2, "a new analysis; the old one stays"
    session.refresh(application)
    assert application.resume_id is None


# --- a report on a CV --------------------------------------------------------------------------


def test_a_cv_report_names_its_file_and_offers_the_tracks_other_cvs(
    client, session, career, provider
):
    make_cv(session, career.first_profile, career.first_track, name="vieja.docx", age_days=9,
            draft=own(career))
    make_cv(session, career.first_profile, career.first_track, name="nueva.docx", age_days=1,
            draft=own(career))
    login(client, career.first.email)

    application = analyse(client, session, career)
    page = client.get(f"/applications/{application.id}").text

    assert "CV analizado: nueva.docx" in page
    assert "Analizado sobre la línea (antes de elegir CV)" not in page
    selector = re.search(r'<select id="reanalyze-cv".*?</select>', page, re.S).group(0)
    assert "vieja.docx" in selector and "nueva.docx" in selector
    assert re.search(rf'<option value="{application.resume_id}"[^>]*selected', selector)
    assert "re-analizar (hasta 2 llamadas)" in page
    career.first.ui_lang = "en"
    session.commit()
    assert "re-analyse (up to 2 calls)" in client.get(f"/applications/{application.id}").text


def test_reanalysing_makes_a_new_application_for_the_same_posting_on_another_cv(
    client, session, career, provider
):
    old = make_cv(session, career.first_profile, career.first_track, name="vieja.docx",
                  age_days=9, draft=own(career))
    make_cv(session, career.first_profile, career.first_track, name="nueva.docx", age_days=1,
            draft=own(career))
    login(client, career.first.email)
    first = analyse(client, session, career, company="Banco Demo 1")

    response = client.post(
        f"/applications/{first.id}/reanalyze", data={"resume_id": str(old.id)},
        follow_redirects=False,
    )

    second = session.query(Application).filter(Application.resume_id == old.id).one()
    assert response.headers["location"] == f"/applications/{second.id}"
    assert second.id != first.id and second.jd_hash == first.jd_hash
    assert second.company == "Banco Demo 1" and second.track_id == first.track_id
    assert second.report["cv"]["filename"] == "vieja.docx"


def test_an_edited_cv_is_said_to_differ_from_the_analysis(client, session, career, provider):
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)
    application = analyse(client, session, career)
    assert "se editó después de este análisis" not in client.get(
        f"/applications/{application.id}"
    ).text
    cv.draft = {**cv.draft, "summary": "Un resumen nuevo"}
    session.commit()

    page = client.get(f"/applications/{application.id}").text

    assert "El CV se editó después de este análisis" in page
    session.refresh(application)
    assert application.report["ceiling"], "the stored ceiling stands"


# --- history -----------------------------------------------------------------------------------


def test_the_history_has_a_cv_column(client, session, career, provider):
    make_cv(session, career.first_profile, career.first_track, name="datos.docx",
            draft=own(career))
    login(client, career.first.email)
    legacy = legacy_application(session, career)
    analysed = analyse(client, session, career)

    rows = {row["id"]: row for row in list_applications(career.first_profile.id, session)}
    page = client.get("/applications").text

    assert rows[analysed.id]["cv"] == "datos.docx" and rows[analysed.id]["cv_deleted"] is False
    assert rows[legacy.id]["cv"] == "" and rows[legacy.id]["cv_deleted"] is False
    assert ">CV<" in page.replace(" ", "").replace("\n", "") or "CV" in page
    assert "datos.docx" in page
    ordered = list_applications(career.first_profile.id, session, sort="cv", direction="desc")
    assert ordered[0]["id"] == analysed.id, "a named CV sorts above none"
    assert client.get("/applications?sort=cv&dir=asc").status_code == 200


def test_the_history_keeps_a_deleted_cvs_name(client, session, career, provider):
    cv = make_cv(session, career.first_profile, career.first_track, name="borrado.docx",
                 draft=own(career))
    login(client, career.first.email)
    application = analyse(client, session, career)
    delete_resume(career.first_profile.id, session, cv.id)
    session.commit()

    (row,) = list_applications(career.first_profile.id, session)

    assert row["id"] == application.id
    assert row["cv"] == "borrado.docx" and row["cv_deleted"] is True


# --- deletion -----------------------------------------------------------------------------------


def test_deleting_a_cv_clears_the_pointer_and_the_analysis_keeps_its_name(
    client, session, career, provider
):
    cv = make_cv(session, career.first_profile, career.first_track, name="borrado.docx",
                 draft=own(career))
    login(client, career.first.email)
    application = analyse(client, session, career)
    assert application.resume_id == cv.id

    response = client.post(f"/import/{cv.id}/delete", follow_redirects=False)

    assert response.status_code == 303
    session.expire_all()
    application = session.get(Application, application.id)
    assert application.resume_id is None, "cleared by code: SQLite does not enforce SET NULL"
    assert application.report["cv"]["filename"] == "borrado.docx"
    page = client.get(f"/applications/{application.id}").text
    assert "CV eliminado: borrado.docx" in page
    assert "Con tu material" in page or "Requisitos y evidencia" in page, "it still renders"


def test_the_confirmation_counts_the_analyses_made_on_the_cv(
    client, session, career, provider
):
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    other = make_cv(session, career.first_profile, career.first_track, name="otro.docx",
                    age_days=5, draft=own(career))
    login(client, career.first.email)
    analyse(client, session, career, resume_id=str(cv.id))
    analyse(client, session, career, resume_id=str(cv.id))
    analyse(client, session, career, resume_id=str(other.id))

    numbers = impact_resume(career.first_profile.id, session, cv.id)
    page = client.get(f"/import/{cv.id}/delete").text

    assert numbers["analyses"] == 2
    assert "2 análisis hechos sobre este CV se conservan con el nombre del archivo" in page
    assert impact_resume(career.first_profile.id, session, other.id)["analyses"] == 1


def test_another_profiles_analyses_are_never_counted(client, session, career, provider):
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    theirs = make_cv(session, career.second_profile, career.second_track, name="suyo.docx")
    session.add(
        Application(
            profile_id=career.second_profile.id,
            resume_id=cv.id,  # a pointer that should never exist; the count is scoped anyway
            jd_text="x",
            jd_hash="sha256:x",
            report={},
            weights_version="w4",
            prompt_versions={},
        )
    )
    session.commit()

    assert impact_resume(career.first_profile.id, session, cv.id)["analyses"] == 0
    assert impact_resume(career.first_profile.id, session, theirs.id) is None
    login(client, career.first.email)
    assert client.get(f"/import/{theirs.id}/delete").status_code == 404


def test_deleting_the_analysis_leaves_the_cv_saved_from_its_attempt(session, career, provider):
    application = legacy_application(session, career)
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_sha256="d" * 64,
        prompt_versions={},
        report={"draft": own(career)},
    )
    session.add(attempt)
    session.commit()
    cv = make_cv(session, career.first_profile, career.first_track, name="intento.docx")
    cv.source_attempt_id = attempt.id
    session.commit()

    delete_application(career.first_profile.id, session, application.id)
    session.commit()

    session.expire_all()
    kept = session.get(Resume, cv.id)
    assert kept is not None and kept.source_attempt_id is None


def test_a_foreign_application_cannot_be_reanalysed(client, session, career, provider):
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)
    application = analyse(client, session, career)
    client.post("/logout")
    login(client, career.second.email)

    response = client.post(f"/applications/{application.id}/reanalyze", data={})

    assert response.status_code == 404
    assert session.query(Application).count() == 1
