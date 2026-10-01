"""F10's acceptance criteria 1-6 (PRD F10.10, C.4).

One test per criterion, as close to the operator's sentence as the server can be
driven without a browser: an unchanged export scores the analysis exactly; a keyword
the user holds raises Keywords towards the ceiling while one they do not hold is
flagged and leaves the ceiling untouched; an invented skill survives "Descartar"; the
ceiling is deterministic and free; the run is server-side, so losing the modal does not
lose the attempt; and no file bytes remain anywhere.
"""

import json
import os
import tempfile

import pytest

from src.attempts import counted_attempts
from src.bullets import create_bullet, list_bullets
from src.extract import client as extract_client
from src.models import ApplicationAttempt, Resume
from src.score.ceiling import compute_ceiling
from src.web.routes import attempts as attempt_routes
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    grading_payload,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes, plain


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
    return session.query(ApplicationAttempt).one()


def test_criterion_1_an_unchanged_export_scores_the_analysis_exactly(
    client, session, career, provider
):
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    before = len(provider.calls_for("EvidenceGrading"))

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    assert len(provider.calls_for("EvidenceGrading")) == before, "served from the cache"
    assert _attempt(session).report["score"] == analysis.report["score"]


def test_criterion_2_a_held_keyword_raises_it_and_an_unheld_one_leaves_the_ceiling(
    client, session, career, provider
):
    held = create_bullet(
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

    # The file claims the keyword the user holds (in a bullet) and one they do not.
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, held.text_es, "Migré el clúster a kubernetes"
    )
    provider.answers["EvidenceGrading"] = grading_payload(None)
    upload(
        client,
        application.id,
        docx_bytes(
            "Experiencia",
            career.first_bullet.text_es,
            held.text_es,
            "Migré el clúster a kubernetes",
        ),
    )

    attempt = _attempt(session)
    before = analysis.report["score"]["sub_scores"]["keywords"]["value"]
    after = attempt.report["score"]["sub_scores"]["keywords"]["value"]
    assert after > before, "the keyword the user holds raises Keywords"
    assert after <= attempt.report["ceiling"]["sub_scores"]["keywords"]["ceiling"]

    # The unheld claim is flagged and the ceiling's own values are the analysis's.
    assert "machine learning" not in attempt.report["flags"]["skills"], "it is held"
    attempt_ceilings = {
        name: row["ceiling"] for name, row in attempt.report["ceiling"]["sub_scores"].items()
    }
    analysis_ceilings = {
        name: row["ceiling"] for name, row in analysis.report["ceiling"]["sub_scores"].items()
    }
    assert attempt_ceilings == analysis_ceilings, (
        "a claim the user cannot support does not move the ceiling"
    )
    assert (
        attempt.report["ceiling"]["fingerprint"] == analysis.report["ceiling"]["fingerprint"]
    ), "and it is the same material"


def test_criterion_3_an_invented_skill_is_flagged_and_survives_discard(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, skills=("machine learning",)
    )
    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    attempt = _attempt(session)
    assert "machine learning" in attempt.report["flags"]["skills"]

    client.post(f"/applications/{application.id}/attempts/{attempt.id}/discard")

    session.expire_all()
    fresh = _attempt(session)
    assert fresh.report["draft"] is None
    assert "machine learning" in fresh.report["flags"]["skills"]


def test_criterion_4_the_ceiling_is_deterministic_and_free(client, session, career, provider):
    from src.documents import master_data
    from src.vocabulary import alias_map

    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    attempt = _attempt(session)
    report = attempt.report
    before = len(provider.calls)

    master = master_data(career.first_profile.id, session, career.first_track)
    aliases = alias_map(session)
    texts = [unit.text for unit in master_texts(career, session)]
    from src.jd import StructuredJD

    jd = StructuredJD(**report["jd"])
    first = compute_ceiling(
        jd, report=report, document_texts=texts, master=master, aliases=aliases
    )
    second = compute_ceiling(
        jd, report=report, document_texts=texts, master=master, aliases=aliases
    )

    assert first == second
    assert len(provider.calls) == before, "no model call"


def master_texts(career, session):
    from src.documents import track_document

    return track_document(career.first_profile.id, session, career.first_track, "es")


def test_criterion_5_the_run_is_server_side_and_reopening_shows_it(
    client, session, career, provider, session_factory, monkeypatch
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    real = attempt_routes.run_pipeline
    observed: dict[str, str] = {}

    def spy(*args, **kwargs):
        with session_factory() as probe:
            observed["status"] = probe.query(ApplicationAttempt).one().status
        return real(*args, **kwargs)

    monkeypatch.setattr(attempt_routes, "run_pipeline", spy)

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    assert observed["status"] == "running", "the row is committed before the work starts"
    attempt = _attempt(session)
    page = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)
    assert "Listo" in page
    assert "Ver el informe completo" in page


def test_criterion_6_no_file_bytes_remain(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    data = docx_bytes("Experiencia", career.first_bullet.text_es)
    before = set(os.listdir(tempfile.gettempdir()))

    upload(client, application.id, data)

    attempt = _attempt(session)
    assert session.query(Resume).count() == 0, "an attempt stores no résumé"
    assert "file_bytes" not in attempt.report
    assert data not in json.dumps(attempt.report, ensure_ascii=False).encode("utf-8")
    assert set(os.listdir(tempfile.gettempdir())) == before
    assert counted_attempts(career.first_profile.id, session, application.id) == 1
    assert len(list_bullets(career.first_profile.id, session, active_only=False)) == 1, (
        "the merge did not run on its own"
    )


def _dated_role(career, session) -> None:
    """The master role gets a start date: the retitled-role match needs one (D5)."""
    from datetime import date

    career.first_role.start_date = date(2020, 3, 1)
    session.commit()


def _retitled(payload: str, title: str = "Data Analyst & RBF Specialist") -> str:
    """The same résumé extraction with every role retitled and dated like the master."""
    data = json.loads(payload)
    for role in data["roles"]:
        role["title"] = title
        role["start_date"] = "2020-03"
    return json.dumps(data)


def test_criterion_1_holds_when_every_role_is_retitled(client, session, career, provider):
    """A tailored CV retitles roles; the same job (employer + start month) is still the
    same job, so the export scores exactly as the analysis and grades nothing (D5)."""
    _dated_role(career, session)
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    before = len(provider.calls_for("EvidenceGrading"))
    provider.answers["ResumeExtraction"] = _retitled(resume_payload(career.first_bullet.text_es))

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    attempt = _attempt(session)
    experience = attempt.report["score"]["sub_scores"]["experience"]
    assert len(provider.calls_for("EvidenceGrading")) == before, "nothing was graded"
    assert attempt.report["score"] == analysis.report["score"]
    assert experience["detail"]["relevant_years"] > 0
    assert [row["by"] for row in attempt.report["role_matching"]] == ["employer_start"]
