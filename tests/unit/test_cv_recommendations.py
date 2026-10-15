"""Recommendations against the CV (PRD F7.2 / F7.5 amended by F11.4).

The master database is the bank; the advice compares it with **the file**: a master
bullet the CV carries — unchanged or reworded — is not advised as missing, one it lacks
that backs a gapped must-have is, and "the first three positions" are the file's.
"""

import json

import pytest

from src.applications import create_application
from src.bullets import create_bullet
from src.cv_analysis import analyze_cv
from src.extract import client as extract_client
from src.keyword_advice import keyword_advice
from tests.conftest import login
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import draft_dict, make_cv

ML_TEXT = "Modelé machine learning para predecir la deserción de clientes"
JD_BOTH_MUST = json.dumps(
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


def grading(*cites: tuple[int, str | None]) -> str:
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
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    stub.answers["JDProposal"] = JD_BOTH_MUST
    stub.answers["GapInterpretation"] = json.dumps(
        {
            "gaps": [{"requirement": "machine learning", "blocking": False, "interpretation": "x"}],
            "warning": {"text": "", "handling": ""},
            "not_found": "",
        }
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


@pytest.fixture
def ml_bullet(session, career):
    bullet = create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()
    return bullet


def run(session, career, *texts):
    cv = make_cv(session, career.first_profile, career.first_track, draft=draft_dict(*texts))
    return analyze_cv(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track,
        resume=cv, chosen="explicit",
    )


def kinds(report):
    return [(item["kind"], item.get("bullet_id")) for item in report["advice"]]


def test_a_master_bullet_outside_the_cv_that_backs_a_gapped_must_have_is_advised(
    session, career, provider, ml_bullet
):
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))

    analysis = run(session, career, career.first_bullet.text_es)

    assert ("add_bullet", str(ml_bullet.id)) in kinds(analysis.report)
    (item,) = [i for i in analysis.report["advice"] if i["kind"] == "add_bullet"]
    assert item["canonical"] == "machine learning" and item["evidence"] == ML_TEXT


def test_a_bullet_already_in_the_cv_is_not_advised(session, career, provider, ml_bullet):
    """The grader may score a bullet low; the CV still carries it."""
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))

    analysis = run(session, career, career.first_bullet.text_es, ML_TEXT)

    assert ("add_bullet", str(ml_bullet.id)) not in kinds(analysis.report)


def test_a_reworded_bullet_is_still_the_cvs_not_a_missing_one(
    session, career, provider, ml_bullet
):
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))

    analysis = run(session, career, career.first_bullet.text_es, f"{ML_TEXT} en 2024")

    assert [row["temporary"] for row in analysis.report["bullets"]] == [False, True]
    assert ("add_bullet", str(ml_bullet.id)) not in kinds(analysis.report)
    assert str(ml_bullet.id) in analysis.report["cv"]["represented_ids"]
    assert str(ml_bullet.id) not in analysis.report["cv"]["matched_ids"]


def test_promote_speaks_of_the_first_three_positions_of_the_file(session, career, provider):
    """The cited must-have is the file's fourth bullet, behind three that show nothing."""
    provider.answers["EvidenceGrading"] = grading((3, str(career.first_bullet.id)), (0, None))
    filler = [f"Participé en la reunión semanal número {n} del área" for n in range(3)]

    analysis = run(session, career, *filler, career.first_bullet.text_es)

    (item,) = [i for i in analysis.report["advice"] if i["kind"] == "promote_bullet"]
    assert item["values"]["position"] == 4
    assert item["bullet_id"] == str(career.first_bullet.id)


def test_the_keywords_card_offers_the_bullet_the_cv_lacks(session, career, provider, ml_bullet):
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))
    analysis = run(session, career, career.first_bullet.text_es)

    card = keyword_advice(
        career.first_profile.id, session, report=analysis.report, track=career.first_track,
        for_file=True,
    )

    machine = [item for item in card.items if item.canonical == "machine learning"]
    assert [item.bullet_id for item in machine] == [str(ml_bullet.id)]
    assert machine[0].basis == "bullet"


def test_the_keywords_card_picks_the_cvs_own_bullet_before_another(
    session, career, provider, ml_bullet
):
    """Two bullets are tagged; the one the CV carries (reworded to drop the term) is the
    one named, so "use it" points at a line the user can already see in the file."""
    other = create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es="Entrené modelos de clasificación para cobranza", text_en=None,
        chips=["machine learning"],
    )
    session.commit()
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))
    analysis = run(session, career, career.first_bullet.text_es, f"{other.text_es} y reportes")

    card = keyword_advice(
        career.first_profile.id, session, report=analysis.report, track=career.first_track,
        for_file=True,
    )

    machine = [item for item in card.items if item.canonical == "machine learning"]
    assert [item.bullet_id for item in machine] == [str(other.id)]


def test_a_cv_report_page_words_its_advice_for_the_file(
    client, session, career, provider, ml_bullet
):
    provider.answers["EvidenceGrading"] = grading((2, str(career.first_bullet.id)), (0, None))
    analysis = run(session, career, career.first_bullet.text_es)
    application = create_application(
        career.first_profile.id, session, jd_text=POSTING, jd_hash=analysis.jd_hash,
        report=analysis.report, weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions, token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "a tu documento" in page, "the add-a-bullet advice speaks of the file"
    assert "machine learning" in page
