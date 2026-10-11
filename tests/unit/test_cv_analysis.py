"""Analysis on a stored CV (PRD F11.2–F11.4): the headline number describes a file.

The provider is stubbed at `client._post`. A CV analysis makes no extraction call for the
CV (its draft is stored), one grading call, the recruiter's queries and the gap prose;
nothing here reads the track's whole selection.
"""

import json

import pytest

from src.analysis import shown_ceiling
from src.attempt_track import build_ephemeral
from src.bullets import create_bullet
from src.cv_analysis import analyze_cv
from src.extract import client as extract_client
from src.ingest.draft import ResumeDraft
from src.models import LlmCall
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import draft_dict, make_cv

ML_TEXT = "Modelé machine learning para predecir la deserción de clientes"
BLOCKER = {
    "cap": 40,
    "cap_reason": "blocker",
    "findings": [
        {"check": "invisible_text", "severity": "blocker", "detail": {"page": 1, "boxes": []}}
    ],
}


def grading(*cites: tuple[int, str | None]) -> str:
    """A grading answer: requirement 0 (python) and 1 (machine learning), by position."""
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
    return json.dumps({"grades": rows, "task_grades": [], "note": "una nota"})


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


@pytest.fixture
def ml_bullet(session, career):
    """A master bullet outside the track's selection, tagged `machine learning`."""
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es=ML_TEXT,
        text_en=None,
        chips=["machine learning"],
    )
    session.commit()
    return bullet


def run(session, career, resume, *, chosen="explicit", jd_text=POSTING):
    return analyze_cv(
        career.first_profile.id,
        session,
        jd_text=jd_text,
        track=career.first_track,
        resume=resume,
        chosen=chosen,
    )


def own(career) -> dict:
    """A draft holding the track's one master bullet, as an unchanged export would."""
    return draft_dict(career.first_bullet.text_es)


def grading_prompt(provider) -> str:
    (call,) = provider.calls_for("EvidenceGrading")[-1:]
    return "\n".join(message["content"] for message in call["messages"])


def test_a_cv_analysis_stores_which_cv_it_scored(session, career, provider):
    cv = make_cv(
        session,
        career.first_profile,
        career.first_track,
        name="cv_a.docx",
        draft=draft_dict(career.first_bullet.text_es),
    )

    analysis = run(session, career, cv, chosen="latest")

    assert analysis.report["cv"]["resume_id"] == str(cv.id)
    assert analysis.report["cv"]["filename"] == "cv_a.docx"
    assert analysis.report["cv"]["chosen"] == "latest"
    assert analysis.report["cv"]["draft_sha"], "the offsets the highlights use are tied to it"
    assert analysis.report["track"]["id"] == str(career.first_track.id)


def test_a_cv_analysis_makes_no_extraction_and_no_scan_call(session, career, provider):
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))

    run(session, career, cv)

    assert provider.calls_for("ResumeExtraction") == [], "the draft is stored (F11.2)"
    purposes = sorted(call.purpose for call in session.query(LlmCall))
    assert purposes == ["boolean_queries", "evidence_grade", "gap_interpret", "jd_extract"]


def test_the_bullet_only_in_cv_b_is_not_credited_to_cv_a(session, career, provider, ml_bullet):
    """F11.11 criterion 1: the track's material is not the file."""
    profile, track = career.first_profile, career.first_track
    cv_a = make_cv(
        session, profile, track, name="a.docx", age_days=5,
        draft=draft_dict(career.first_bullet.text_es),
    )
    cv_b = make_cv(
        session, profile, track, name="b.docx", age_days=1,
        draft=draft_dict(career.first_bullet.text_es, ML_TEXT),
    )

    # CV A holds only the first bullet: citing the other one would be a citation
    # violation, so the stub answers what a faithful grader would (no evidence for ML).
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))
    analysis_a = run(session, career, cv_a)
    prompt_a = grading_prompt(provider)
    provider.answers["EvidenceGrading"] = grading(
        (2, str(career.first_bullet.id)), (2, str(ml_bullet.id))
    )
    provider.answers["GapInterpretation"] = json.dumps(
        {"gaps": [], "warning": {"text": "", "handling": ""}, "not_found": ""}
    )
    analysis_b = run(session, career, cv_b)
    prompt_b = grading_prompt(provider)

    assert ML_TEXT not in prompt_a and ML_TEXT in prompt_b
    levels_a = {g["requirement"]: g["level"] for g in analysis_a.report["grades"]}
    levels_b = {g["requirement"]: g["level"] for g in analysis_b.report["grades"]}
    assert levels_a["machine learning"] == 0 and levels_b["machine learning"] == 2
    assert (
        analysis_b.report["score"]["capped"] > analysis_a.report["score"]["capped"]
    ), "a file with more evidence scores higher"
    assert str(ml_bullet.id) not in {s["id"] for s in analysis_a.report["bullets"]}
    assert str(ml_bullet.id) in {s["id"] for s in analysis_b.report["bullets"]}


def test_a_clean_cv_is_not_capped_by_another_cvs_blocker(session, career, provider):
    """F11.11 criterion 2: the readability cap is the CV's own."""
    profile, track = career.first_profile, career.first_track
    blocked = make_cv(
        session, profile, track, name="blocked.docx", age_days=1, gate=BLOCKER, draft=own(career)
    )
    clean = make_cv(
        session, profile, track, name="clean.docx", age_days=9,
        gate={"cap": None, "findings": []}, draft=own(career),
    )

    on_blocked = run(session, career, blocked).report["score"]
    on_clean = run(session, career, clean).report["score"]

    assert on_blocked["capped"] <= 40 and on_blocked["capped"] < on_blocked["uncapped"]
    assert on_clean["capped"] == on_clean["uncapped"]


def test_a_cv_without_a_gate_is_uncapped_not_borrowed(session, career, provider):
    """The newest upload of the track carries a blocker; a CV with no gate is not capped."""
    profile, track = career.first_profile, career.first_track
    make_cv(session, profile, track, name="upload.docx", age_days=1, gate=BLOCKER)
    saved = make_cv(
        session, profile, track, name="saved.docx", age_days=0, gate=None, draft=own(career)
    )

    score = run(session, career, saved).report["score"]

    assert score["capped"] == score["uncapped"]
    assert run(session, career, saved).report["gate"] is None


def test_a_bullet_missing_from_the_master_is_scored_with_a_temporary_id(
    session, career, provider
):
    new_text = "Automaticé el cierre mensual con scripts propios"
    cv = make_cv(
        session, career.first_profile, career.first_track,
        draft=draft_dict(career.first_bullet.text_es, new_text),
    )
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))

    analysis = run(session, career, cv)

    snapshots = analysis.report["bullets"]
    assert [s["temporary"] for s in snapshots] == [False, True]
    assert snapshots[1]["text"] == new_text, "the text is snapshotted into the report"
    assert [s["ordinal"] for s in snapshots] == [0, 1], "file order, for the highlight map"
    assert new_text in grading_prompt(provider)


def test_the_ceiling_is_stable_on_view_even_with_temporary_bullets(session, career, provider):
    """Temporary ids change every run; the fingerprint reads the master-matched ones only."""
    new_text = "Automaticé el cierre mensual con scripts propios"
    cv = make_cv(
        session, career.first_profile, career.first_track,
        draft=draft_dict(career.first_bullet.text_es, new_text),
    )
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))
    analysis = run(session, career, cv)

    ceiling, recomputed = shown_ceiling(
        career.first_profile.id, session, report=analysis.report, track=career.first_track
    )

    assert recomputed is False
    assert ceiling == analysis.report["ceiling"]
    assert analysis.report["ceiling"]["low"] >= analysis.report["score"]["capped"]


def test_the_ceiling_reads_the_whole_master_against_the_cv(
    session, career, provider, ml_bullet
):
    cv = make_cv(
        session, career.first_profile, career.first_track,
        draft=draft_dict(career.first_bullet.text_es),
    )
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))

    analysis = run(session, career, cv)

    skills = analysis.report["ceiling"]["sub_scores"]["skills"]
    assert skills["ceiling"] > skills["current"], "the ML bullet outside the CV lifts the ceiling"


def test_a_stored_ceiling_stands_when_the_cv_is_gone(session, career, provider):
    cv = make_cv(session, career.first_profile, career.first_track, draft=own(career))
    analysis = run(session, career, cv)
    stored = analysis.report["ceiling"]
    session.delete(cv)
    session.commit()

    ceiling, recomputed = shown_ceiling(
        career.first_profile.id, session, report=analysis.report, track=career.first_track
    )

    assert ceiling == stored and recomputed is False


def test_a_file_in_the_other_language_raises_the_f42_alert(session, career, provider):
    english = make_cv(
        session, career.first_profile, career.first_track,
        draft=draft_dict(career.first_bullet.text_es, language="en", headline="Data analyst"),
    )
    spanish = make_cv(
        session, career.first_profile, career.first_track, name="es.docx", age_days=3,
        draft=draft_dict(career.first_bullet.text_es, language="es"),
    )

    on_english = run(session, career, english).report["gaps"]["alerts"]
    on_spanish = run(session, career, spanish).report["gaps"]["alerts"]

    (alert,) = [a for a in on_english if a["kind"] == "language_mismatch"]
    assert alert["posting"] == "es" and alert["other"] == "en"
    assert alert["fallback_bullets"] == 1 and alert["bullets"] == 1
    assert [a for a in on_spanish if a["kind"] == "language_mismatch"] == []


def test_a_repeat_analysis_of_the_same_cv_costs_nothing_new(session, career, provider):
    cv = make_cv(
        session, career.first_profile, career.first_track,
        draft=draft_dict(career.first_bullet.text_es),
    )
    first = run(session, career, cv)
    calls = len(provider.calls)

    second = run(session, career, cv)

    assert len(provider.calls) == calls, "every call is answered by the cache"
    assert second.report["score"] == first.report["score"]


def test_a_reworded_bullet_still_represents_its_master_row(session, career):
    """F7.2 and F11.5 ask whether a master bullet is in the CV: a reworded one is."""
    reworded = f"{career.first_bullet.text_es} y SQL"
    draft = ResumeDraft.model_validate(draft_dict(reworded))

    result = build_ephemeral(
        career.first_profile.id, session, track=career.first_track, lang="es", draft=draft
    )

    assert [row.temporary for row in result.snapshots] == [True]
    assert result.represented_ids == (str(career.first_bullet.id),)
