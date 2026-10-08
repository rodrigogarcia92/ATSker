"""A summary for the attempt's file, copy-only (PRD F10.7, queue P6)."""

import uuid

import pytest

from src.extract import client as extract_client
from src.generate.proposals import attempt_summary_material
from src.models import ApplicationAttempt, Summary, Track
from src.summaries import create_summary
from src.tracks import set_track_summary
from tests.conftest import login
from tests.unit.test_generation import stored_application
from tests.unit.test_summary_v4 import GOOD, Queue

FILE_SUMMARY = "Analista de datos con más de ocho años y machine learning."
TEMP_ID = "tmp-1"


def report(*, summary=FILE_SUMMARY, skills=("machine learning",)):
    return {
        "grades": [
            {
                "requirement": "python",
                "must_have": True,
                "level": 3,
                "basis": "direct",
                "bullet_id": TEMP_ID,
            }
        ],
        "bullets": [
            {
                "id": TEMP_ID,
                "temporary": True,
                "role_id": "r",
                "text": "Automaticé el reporte con Python",
            }
        ],
        "draft": (
            None
            if summary is None
            else {"language": "es", "summary": summary, "skills": list(skills), "roles": []}
        ),
        "flags": {},
    }


def make_attempt(session, career, application, *, status="done", body=None):
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status=status,
        file_sha256="e" * 64,
        prompt_versions={},
        report=body if body is not None else report(),
    )
    session.add(attempt)
    session.commit()
    return attempt


def urls(application, attempt):
    base = f"/applications/{application.id}/attempts/{attempt.id}/summary"
    return base, f"{base}/generate"


@pytest.fixture
def queue(monkeypatch, test_settings, career):
    def make(*texts, cites):
        stub = Queue(*texts, cites=cites)
        monkeypatch.setattr(extract_client, "_post", stub)
        return stub

    return make


def test_the_prompt_base_is_the_files_own_summary_and_its_cite_passes(
    client, session, career, queue
):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    stub = queue(GOOD, cites=[TEMP_ID, f"summary:attempt-{attempt.id}"])
    login(client, career.first.email)

    page = client.post(urls(application, attempt)[1]).text

    assert len(stub.calls) == 1
    assert f"summary:attempt-{attempt.id}" in stub.user() and "ocho años" in stub.user()
    assert "Basado en el resumen de tu documento" in page
    assert "no pasa la validación" not in page, "the file's base and bullet are supplied sources"
    assert "<textarea" in page and "Copiar" in page
    assert "Pégalo en tu documento; no se guarda en tu material" in page


def test_the_material_for_a_file(client, session, career):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)

    material = attempt_summary_material(career.first_profile.id, session, application, attempt)

    assert material.base.origin == "file"
    assert material.base.summary_id == f"attempt-{attempt.id}"
    assert material.bullets == [(TEMP_ID, "Automaticé el reporte con Python")]
    assert "machine learning" in material.pool, "a skill only the file's skills list names"
    assert "python" in material.pool
    assert material.grades == [{"level": 3, "evidence_id": TEMP_ID}]
    assert material.title == "Analista de datos" and material.language == "es"


def test_a_skill_named_only_in_the_files_skills_list_passes_closure(
    client, session, career, queue
):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    stub = queue(
        "Analista de datos con Python y machine learning.",
        cites=[TEMP_ID, f"summary:attempt-{attempt.id}"],
    )
    login(client, career.first.email)

    page = client.post(urls(application, attempt)[1]).text

    assert len(stub.calls) >= 1
    assert "no pasa la validación" not in page


def test_a_discarded_draft_falls_back_to_the_tracks_summary(client, session, career, queue):
    pid = career.first_profile.id
    base = create_summary(pid, session, text="Analista con base de línea.", lang="es")
    set_track_summary(pid, session, career.first_track.id, lang="es", summary_id=base.id)
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application, body=report(summary=None))
    stub = queue(GOOD, cites=[TEMP_ID, f"summary:{base.id}"])
    login(client, career.first.email)

    page = client.post(urls(application, attempt)[1]).text

    assert f"summary:{base.id}" in stub.user()
    assert "Basado en el resumen de tu línea" in page


def test_a_temporary_bullet_id_is_a_valid_cite(client, session, career, queue):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    queue(GOOD, cites=[TEMP_ID])
    login(client, career.first.email)

    page = client.post(urls(application, attempt)[1]).text

    assert "no pasa la validación" not in page


def test_the_get_never_calls_the_provider(client, session, career, queue):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    stub = queue(GOOD, cites=[TEMP_ID])
    login(client, career.first.email)

    shell = client.get(urls(application, attempt)[0])

    assert shell.status_code == 200 and stub.calls == []
    assert "Generar propuesta" in shell.text
    assert f"/attempts/{attempt.id}/summary/generate" in shell.text


@pytest.mark.parametrize("status", ["running", "failed"])
def test_an_attempt_that_is_not_done_is_a_404(client, session, career, queue, status):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application, status=status)
    stub = queue(GOOD, cites=[TEMP_ID])
    login(client, career.first.email)

    get_url, post_url = urls(application, attempt)

    assert client.get(get_url).status_code == 404
    assert client.post(post_url).status_code == 404
    assert stub.calls == []


def test_a_foreign_application_or_attempt_is_a_404(client, session, career, queue):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    other = stored_application(session, career)
    stub = queue(GOOD, cites=[TEMP_ID])

    login(client, career.second.email)
    foreign = urls(application, attempt)
    assert client.get(foreign[0]).status_code == 404
    assert client.post(foreign[1]).status_code == 404

    client.cookies.clear()
    login(client, career.first.email)
    crossed = urls(other, attempt)  # the attempt belongs to another application
    assert client.get(crossed[0]).status_code == 404
    assert client.post(crossed[1]).status_code == 404
    missing = f"/applications/{application.id}/attempts/{uuid.uuid4()}/summary"
    assert client.get(missing).status_code == 404
    assert stub.calls == []


def test_nothing_the_user_owns_changes(client, session, career, queue):
    application = stored_application(session, career)
    attempt = make_attempt(session, career, application)
    queue(GOOD, cites=[TEMP_ID, f"summary:attempt-{attempt.id}"])
    login(client, career.first.email)

    def snapshot():
        session.expire_all()
        return (
            sorted((s.id, s.text, s.lang) for s in session.query(Summary)),
            sorted(
                (t.id, t.summary_es_id, t.summary_en_id, tuple(t.skills))
                for t in session.query(Track)
            ),
            sorted(
                (a.id, a.status, str(a.report), a.is_sent, a.job_match)
                for a in session.query(ApplicationAttempt)
            ),
        )

    before = snapshot()
    client.get(urls(application, attempt)[0])
    answer = client.post(urls(application, attempt)[1])

    assert answer.status_code == 200
    assert snapshot() == before


def test_the_result_shows_the_button_for_a_done_attempt_only(client, session, career):
    application = stored_application(session, career)
    done = make_attempt(session, career, application)
    failed = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=2,
        status="failed",
        error="x",
        file_sha256="f" * 64,
        prompt_versions={},
        report={},
    )
    session.add(failed)
    session.commit()
    login(client, career.first.email)

    done_page = client.get(f"/applications/{application.id}/attempts/{done.id}").text
    failed_page = client.get(f"/applications/{application.id}/attempts/{failed.id}").text

    assert "Proponer resumen para este documento" in done_page
    assert f"/attempts/{done.id}/summary" in done_page
    assert "Proponer resumen para este documento" not in failed_page
