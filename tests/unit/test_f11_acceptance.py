"""F11.11 acceptance, criteria 1–8 (PRD F11.11); criterion 9 is the operator's, on a phone.

Each test drives the product the way a user does — the form, the report page, the attempt
modal — against a stubbed provider, and states the criterion it answers. The unit-level
proofs sit beside the code (`test_cv_analysis`, `test_requirement_notes`, `test_cvs`,
`test_save_attempt_as_cv`, `test_analyze_cv_form`, `test_cv_lifecycle`); this module is the
one place the eight read together.
"""

import json
import uuid

import pytest

from src.analysis import analyze
from src.applications import create_application
from src.bullets import create_bullet
from src.documents import master_data
from src.extract import client as extract_client
from src.models import Application, ApplicationAttempt, LlmCall, Resume
from src.resumes import latest_cv
from src.score.ceiling import _family_siblings, requirement_support
from src.tracks import create_track, set_track_bullets
from src.vocabulary import alias_map
from tests.conftest import login
from tests.unit.attempt_support import (
    POSTING,
    AttemptProvider,
    analyzed_application,
    resume_payload,
)
from tests.unit.cv_support import draft_dict, make_cv
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes

ML_TEXT = "Modelé machine learning para predecir la deserción de clientes"
BLOCKER = {
    "cap": 40,
    "cap_reason": "blocker",
    "findings": [{"check": "invisible_text", "severity": "blocker", "detail": {"page": 1}}],
}
JD_MUST_ML = json.dumps(
    {
        "language": "es",
        "title": "Analista de datos",
        "seniority": "mid",
        "years_required": 3,
        "must_have": ["python", "machine learning"],
        "nice_to_have": [],
        "raw_keywords": ["reportes"],
        "hard_requirements": [],
        "location_policy": "hybrid_lima",
        "responsibilities": [],
    }
)
NO_GAPS = json.dumps({"gaps": [], "warning": {"text": "", "handling": ""}, "not_found": ""})


def grades(*cites: tuple[int, str | None]) -> str:
    rows = []
    for index, (level, evidence_id) in enumerate(cites):
        if evidence_id is None:
            rows.append({"index": index, "level": 0, "basis": "none", "source": None})
        else:
            rows.append(
                {
                    "index": index,
                    "level": level,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": evidence_id,
                    "transfer_reason": None,
                }
            )
    return json.dumps({"grades": rows, "task_grades": [], "note": "nota"})


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def post(client, career, **fields):
    return client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id), **fields},
        follow_redirects=False,
    )


def application_at(session, response) -> Application:
    return session.get(Application, uuid.UUID(response.headers["location"].rsplit("/", 1)[1]))


def grading_prompt(provider) -> str:
    call = provider.calls_for("EvidenceGrading")[-1]
    return "\n".join(message["content"] for message in call["messages"])


def own(career) -> dict:
    return draft_dict(career.first_bullet.text_es)


def test_criterion_1_a_bullet_only_in_cv_b_is_not_credited_to_cv_a(
    client, session, career, provider
):
    """A's requirement note and recommendations name it."""
    ml = create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()
    cv_a = make_cv(session, career.first_profile, career.first_track, name="a.docx", age_days=5,
                   draft=own(career))
    make_cv(session, career.first_profile, career.first_track, name="b.docx", age_days=1,
            draft=draft_dict(career.first_bullet.text_es, ML_TEXT))
    provider.answers["JDProposal"] = JD_MUST_ML
    provider.answers["EvidenceGrading"] = grades((2, str(career.first_bullet.id)), (0, None))
    login(client, career.first.email)

    application = application_at(session, post(client, career, resume_id=str(cv_a.id)))

    assert ML_TEXT not in grading_prompt(provider), "CV A does not carry it, so it is not read"
    levels = {g["requirement"]: g["level"] for g in application.report["grades"]}
    assert levels["machine learning"] == 0
    (note,) = application.report["requirement_notes"]
    assert note["bullet_id"] == str(ml.id) and note["bullet_text"] == ML_TEXT
    advice = [(i["kind"], i["bullet_id"]) for i in application.report["advice"]]
    assert ("add_bullet", str(ml.id)) in advice
    page = client.get(f"/applications/{application.id}").text
    assert ML_TEXT in page and "Con tu material" in page


def test_criterion_2_a_clean_cv_is_not_capped_by_another_cvs_blocker(
    client, session, career, provider
):
    blocked = make_cv(session, career.first_profile, career.first_track, name="blocked.docx",
                      age_days=1, gate=BLOCKER, draft=own(career))
    clean = make_cv(session, career.first_profile, career.first_track, name="clean.docx",
                    age_days=9, gate={"cap": None, "findings": []}, draft=own(career))
    login(client, career.first.email)

    on_clean = application_at(session, post(client, career, resume_id=str(clean.id)))
    on_blocked = application_at(session, post(client, career, resume_id=str(blocked.id)))

    assert on_clean.report["score"]["capped"] == on_clean.report["score"]["uncapped"]
    assert on_blocked.report["score"]["capped"] <= 40
    assert on_blocked.report["score"]["capped"] < on_blocked.report["score"]["uncapped"]


def test_criterion_3_latest_resolves_to_the_newest_cv_at_submit(client, session, career, provider):
    older = make_cv(session, career.first_profile, career.first_track, name="old.docx",
                    age_days=9, draft=own(career))
    login(client, career.first.email)
    first = application_at(session, post(client, career, resume_id="latest"))
    newer = make_cv(session, career.first_profile, career.first_track, name="new.docx",
                    age_days=1, draft=own(career))

    second = application_at(session, post(client, career, resume_id="latest"))

    assert first.resume_id == older.id and second.resume_id == newer.id
    assert latest_cv(career.first_profile.id, session, career.first_track.id).id == newer.id
    assert second.report["cv"]["chosen"] == "latest"


def test_criterion_4_an_attempt_saved_to_the_track_scores_exactly_as_the_attempt(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    extra = "Automaticé el cierre mensual con scripts propios"
    provider.answers["ResumeExtraction"] = resume_payload(career.first_bullet.text_es, extra)
    client.post(
        f"/applications/{application.id}/attempts",
        files={"file": ("cv.docx", docx_bytes("Experiencia", career.first_bullet.text_es, extra),
                        DOCX_TYPE)},
    )
    attempt = session.query(ApplicationAttempt).one()
    client.post(f"/applications/{application.id}/attempts/{attempt.id}/save-cv")
    resume = session.query(Resume).filter(Resume.source_attempt_id == attempt.id).one()
    grading_calls = len(provider.calls_for("EvidenceGrading"))

    response = client.post(
        f"/applications/{application.id}/reanalyze", data={"resume_id": str(resume.id)},
        follow_redirects=False,
    )

    analysed = application_at(session, response)
    assert analysed.report["score"] == attempt.report["score"]
    assert len(provider.calls_for("EvidenceGrading")) == grading_calls, "zero grading calls"


def test_criterion_5_the_note_agrees_with_the_ceiling_and_job_match_ignores_it(
    client, session, career, provider, monkeypatch
):
    create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    provider.answers["JDProposal"] = JD_MUST_ML
    provider.answers["EvidenceGrading"] = grades((2, str(career.first_bullet.id)), (0, None))
    login(client, career.first.email)
    with_notes = application_at(session, post(client, career, resume_id=str(cv.id)))

    report = with_notes.report
    master = master_data(career.first_profile.id, session, career.first_track)
    supports = requirement_support(
        report["grades"], master, alias_map(session), _family_siblings(master),
        report["cv"]["represented_ids"],
    )
    noted = {note["requirement"] for note in report["requirement_notes"]}
    for support in supports:
        # lifted by the ceiling's rule == noted, or the only support is inside the CV
        assert support.lifted == (support.requirement in noted) or support.in_document, support
    skills = report["ceiling"]["sub_scores"]["skills"]
    assert skills["ceiling"] > skills["current"], "the ceiling lifted what the note names"

    monkeypatch.setattr("src.analysis.requirement_notes", lambda *args, **kwargs: [])
    without = application_at(session, post(client, career, resume_id=str(cv.id)))
    assert json.dumps(report["score"], sort_keys=True) == json.dumps(
        without.report["score"], sort_keys=True
    ), "byte-identical with and without notes"


def test_criterion_6_no_get_calls_the_provider_and_propose_costs_one_call_then_none(
    client, session, career, provider
):
    other = create_track(career.first_profile.id, session, name="BI Analyst",
                         applies_when="BI", lang="en")
    set_track_bullets(career.first_profile.id, session, other.id, [career.first_bullet.id])
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    make_cv(session, career.first_profile, other, name="bi.docx", draft=own(career))
    session.commit()
    login(client, career.first.email)
    done = application_at(session, post(client, career))
    calls = len(provider.calls)
    for url in (
        "/analyze",
        f"/analyze?track_id={career.first_track.id}",
        f"/analyze/cvs?track_id={other.id}",
        f"/analyze?application={done.id}",
        f"/applications/{done.id}",
        f"/applications/{done.id}/summary",
        f"/applications/{done.id}/summary?dialog=1",
        "/applications",
    ):
        assert client.get(url).status_code == 200, url
    assert len(provider.calls) == calls, "no GET reached the provider"

    session.query(LlmCall).delete()
    session.commit()
    before = len(provider.calls)
    client.post("/analyze/propose-track", data={"jd_text": POSTING})
    after_first = len(provider.calls)
    client.post("/analyze/propose-track", data={"jd_text": POSTING})

    assert after_first - before <= 1, "at most the JD extraction"
    assert len(provider.calls) == after_first, "none on repeat"


def test_criterion_7_a_report_stored_before_f11_renders_unchanged_with_its_label(
    client, session, career, provider
):
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING, track=career.first_track)
    stored = create_application(
        career.first_profile.id, session, jd_text=POSTING, jd_hash=analysis.jd_hash,
        report=analysis.report, weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions, token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    before = json.dumps(stored.report, sort_keys=True)
    login(client, career.first.email)

    page = client.get(f"/applications/{stored.id}").text

    assert "Analizado sobre la línea (antes de elegir CV)" in page
    session.refresh(stored)
    assert json.dumps(stored.report, sort_keys=True) == before
    assert stored.resume_id is None


def test_criterion_8_a_foreign_resume_id_is_a_404_from_the_form_the_url_and_the_selector(
    client, session, career, provider
):
    theirs = make_cv(session, career.second_profile, career.second_track, name="theirs.docx")
    make_cv(session, career.first_profile, career.first_track, draft=own(career))
    login(client, career.first.email)
    mine = application_at(session, post(client, career))
    calls = len(provider.calls)

    form = post(client, career, resume_id=str(theirs.id))
    selector = client.post(f"/applications/{mine.id}/reanalyze", data={"resume_id": str(theirs.id)})
    url = client.get(f"/analyze/cvs?track_id={career.second_track.id}")

    assert form.status_code == selector.status_code == url.status_code == 404
    assert len(provider.calls) == calls, "refused before anything was paid for"
    assert session.query(Application).count() == 1
