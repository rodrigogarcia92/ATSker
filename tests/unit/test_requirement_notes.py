"""The requirement note (PRD F11.5): the potential with all the user's material.

The note and the Skills ceiling are one rule (`requirement_support`), so they cannot
disagree; the note never reaches a score. The pure tests build the master data by hand;
the integration tests run a real CV analysis.
"""

import itertools
import json

import pytest

from src.applications import create_application
from src.bullets import create_bullet
from src.cv_analysis import analyze_cv
from src.extract import client as extract_client
from src.score.ceiling import (
    MasterBullet,
    MasterData,
    MasterRole,
    _family_siblings,
    requirement_notes,
    requirement_support,
)
from src.score.evidence import Level, evidence_coverage
from src.score.weights import W4
from tests.conftest import login
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import draft_dict, make_cv

ALIASES = {"python": "python", "tableau": "tableau", "power bi": "power bi", "sql": "sql"}
FAMILIES = {"tableau": "bi", "power bi": "bi"}
ROLE = MasterRole("role-1", "Analista", "Analyst", None, None, ("b-in", "b-out", "b-sib"))


def bullet(bullet_id: str, *skills: str, es: str = "texto", en: str | None = None):
    return MasterBullet(bullet_id, "role-1", es, en, tuple(skills))


def master(*bullets: MasterBullet) -> MasterData:
    return MasterData(
        bullets=tuple(bullets), roles=(ROLE,), headlines=(), pool=(), families=FAMILIES
    )


def grade(requirement: str, level: int, must_have: bool = True, basis: str = "direct"):
    return {"requirement": requirement, "level": level, "must_have": must_have, "basis": basis}


def test_a_requirement_below_two_is_noted_when_outside_material_is_tagged():
    data = master(bullet("b-out", "python", es="Automaticé reportes con Python"))

    (note,) = requirement_notes([grade("python", 0)], data, ALIASES, (), "es")

    assert note["requirement"] == "python"
    assert (note["level"], note["estimated_level"], note["basis"]) == (0, 2, "direct")
    assert note["bullet_id"] == "b-out"
    assert note["bullet_text"] == "Automaticé reportes con Python"
    assert note["role"] == "Analista" and note["role_id"] == "role-1"


def test_the_note_reads_in_the_postings_language_with_a_fallback():
    data = master(bullet("b-out", "python", es="Texto es", en="Text en"))

    (english,) = requirement_notes([grade("python", 1)], data, ALIASES, (), "en")
    (spanish,) = requirement_notes([grade("python", 1)], data, ALIASES, (), "es")

    assert (english["bullet_text"], english["role"]) == ("Text en", "Analyst")
    assert (spanish["bullet_text"], spanish["role"]) == ("Texto es", "Analista")


def test_a_requirement_already_at_two_gets_no_note():
    data = master(bullet("b-out", "python"))

    both = [grade("python", 2), grade("python", 3)]
    assert requirement_notes(both, data, ALIASES, (), "es") == []


def test_a_family_sibling_gives_an_equivalent_note():
    data = master(bullet("b-sib", "power bi"))

    (note,) = requirement_notes([grade("tableau", 1)], data, ALIASES, (), "es")

    assert (note["estimated_level"], note["basis"], note["bullet_id"]) == (2, "equivalent", "b-sib")


def test_support_found_only_inside_the_cv_lifts_the_ceiling_but_makes_no_note():
    data = master(bullet("b-in", "python"))

    (support,) = requirement_support(
        [grade("python", 1)], data, ALIASES, _family_siblings(data), {"b-in"}
    )

    assert support.lifted and support.in_document and not support.note
    assert requirement_notes([grade("python", 1)], data, ALIASES, {"b-in"}, "es") == []


def test_outside_material_is_preferred_over_the_cvs_own():
    data = master(bullet("b-in", "python"), bullet("b-out", "python"))

    (note,) = requirement_notes([grade("python", 0)], data, ALIASES, {"b-in"}, "es")

    assert note["bullet_id"] == "b-out"


def test_an_outside_sibling_is_noted_even_when_the_canonical_is_tagged_inside():
    data = master(bullet("b-in", "tableau"), bullet("b-sib", "power bi"))

    (support,) = requirement_support(
        [grade("tableau", 1)], data, ALIASES, _family_siblings(data), {"b-in"}
    )

    assert support.lifted_level == 2 and support.basis == "direct", "the ceiling's own reading"
    assert support.note and support.bullet_id == "b-sib" and support.note_basis == "equivalent"


def test_nothing_tagged_means_nothing_to_say():
    data = master(bullet("b-out", "sql"))

    assert requirement_notes([grade("python", 0)], data, ALIASES, (), "es") == []


def _reference_lift(level: int, basis: str, canonical: str, data: MasterData) -> tuple[int, str]:
    """The Skills rule exactly as `_skills_ceiling` wrote it before F11.5 factored it."""
    tagged = {skill for item in data.bullets for skill in item.skills}
    siblings = _family_siblings(data)
    if level < 2:
        if canonical in tagged:
            return 2, "direct"
        if siblings.get(canonical, set()) & tagged:
            return 2, "equivalent"
    return level, basis


@pytest.mark.parametrize(
    ("tags", "level", "requirement"),
    list(
        itertools.product(
            [(), ("python",), ("power bi",), ("tableau", "sql"), ("sql",)],
            [0, 1, 2, 3],
            ["python", "tableau", "sql"],
        )
    ),
)
def test_the_support_rule_is_the_ceilings_rule_on_every_requirement(tags, level, requirement):
    data = master(bullet("b-out", *tags))

    (support,) = requirement_support(
        [grade(requirement, level, basis="transferable")],
        data,
        ALIASES,
        _family_siblings(data),
        (),
    )

    assert (support.lifted_level, support.basis) == _reference_lift(
        level, "transferable", requirement, data
    )


# --- through a real CV analysis -------------------------------------------------------

ML_TEXT = "Modelé machine learning para predecir la deserción de clientes"


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _cv_analysis(session, career, *texts):
    cv = make_cv(
        session, career.first_profile, career.first_track, draft=draft_dict(*texts)
    )
    return analyze_cv(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track,
        resume=cv, chosen="explicit",
    )


def test_a_cv_analysis_notes_the_bullet_it_does_not_carry(session, career, provider):
    ml = create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()

    analysis = _cv_analysis(session, career, career.first_bullet.text_es)

    (note,) = analysis.report["requirement_notes"]
    assert note["requirement"] == "machine learning"
    assert note["bullet_id"] == str(ml.id) and note["bullet_text"] == ML_TEXT
    assert note["role"] == "Analista de datos" and note["basis"] == "direct"


def test_the_note_agrees_with_the_ceiling_on_every_requirement(session, career, provider):
    create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()

    analysis = _cv_analysis(session, career, career.first_bullet.text_es)

    noted = {note["requirement"] for note in analysis.report["requirement_notes"]}
    levels = [
        Level(
            grade["requirement"],
            2 if grade["requirement"] in noted else grade["level"],
            grade["must_have"],
            "direct" if grade["requirement"] in noted else grade["basis"],
        )
        for grade in analysis.report["grades"]
    ]
    expected = evidence_coverage(levels, basis_credit=W4.basis_credit).value
    skills = analysis.report["ceiling"]["sub_scores"]["skills"]
    assert skills["ceiling"] == round(max(skills["current"], expected), 4)


def test_job_match_is_byte_identical_with_and_without_notes(
    session, career, provider, monkeypatch
):
    create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()
    with_notes = _cv_analysis(session, career, career.first_bullet.text_es)
    monkeypatch.setattr("src.analysis.requirement_notes", lambda *args, **kwargs: [])

    without = _cv_analysis(session, career, career.first_bullet.text_es)

    assert with_notes.report["requirement_notes"] and without.report["requirement_notes"] == []
    dump = lambda report: json.dumps(report["score"], sort_keys=True)  # noqa: E731
    assert dump(with_notes.report) == dump(without.report)
    assert with_notes.report["ceiling"] == without.report["ceiling"]


def test_the_report_page_shows_the_note_and_counts_it(client, session, career, provider):
    create_bullet(
        career.first_profile.id, session, role_id=career.first_role.id,
        text_es=ML_TEXT, text_en=None, chips=["machine learning"],
    )
    session.commit()
    analysis = _cv_analysis(session, career, career.first_bullet.text_es)
    application = create_application(
        career.first_profile.id, session, jd_text=POSTING, jd_hash=analysis.jd_hash,
        report=analysis.report, weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions, token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "Con tu material: nivel 2 (estimado)" in page
    assert ML_TEXT in page and "no está en este CV" in page
    assert "1 podría subir con tu material" in page
    career.first.ui_lang = "en"
    session.commit()
    english = client.get(f"/applications/{application.id}").text
    assert "With your material: level 2 (estimated)" in english
    assert "1 could rise with your material" in english
