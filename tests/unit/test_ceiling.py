"""The ceiling, one or more tests per sub-score (PRD F10.2, A1/A2/A3/A10).

Each sub-score's rule is exercised on a hand-built report and master so the number is
exactly predictable: a held keyword lifts Keywords and an unheld one cannot; the title
ceiling is the best held role title and a headline that copies the posting title adds
nothing; a requirement below level 2 is lifted by a tag, direct or through a family
sibling, while one already at 2 or more stays; an off-track role with a tagged bullet
becomes relevant. The whole function is deterministic and touches no provider.
"""

from datetime import date

import pytest

from src.analysis import analyze
from src.documents import master_data
from src.extract import client as extract_client
from src.jd import StructuredJD
from src.score.ceiling import (
    EXACT,
    MasterBullet,
    MasterData,
    MasterRole,
    compute_ceiling,
)
from src.vocabulary import alias_map
from tests.unit.test_analysis import POSTING, Provider


def _sub(value, matched=(), missing=(), detail=None):
    return {
        "value": value,
        "matched": list(matched),
        "missing": list(missing),
        "detail": detail or {},
    }


def _report(grades=(), sub_scores=None, version="w4"):
    return {
        "grades": list(grades),
        "score": {"weights_version": version, "sub_scores": sub_scores or {}},
    }


def _master(bullets=(), roles=(), headlines=(), pool=(), families=None):
    return MasterData(
        bullets=tuple(bullets),
        roles=tuple(roles),
        headlines=tuple(headlines),
        pool=tuple(pool),
        families=families or {},
    )


def _bullet(bullet_id, role_id, *, skills=(), text_es=None, text_en=None):
    return MasterBullet(
        id=bullet_id,
        role_id=role_id,
        text_es=text_es,
        text_en=text_en,
        skills=tuple(skills),
    )


def _role(role_id, *, title_es=None, title_en=None, start=None, end=None, bullet_ids=()):
    return MasterRole(
        id=role_id,
        title_es=title_es,
        title_en=title_en,
        start_date=start,
        end_date=end,
        bullet_ids=tuple(bullet_ids),
    )


# --- Keywords (0.15) --------------------------------------------------------------


def test_a_held_keyword_lifts_the_keyword_ceiling():
    jd = StructuredJD(title="X", must_have=["python"])
    report = _report(sub_scores={"keywords": _sub(0.0)})
    master = _master(pool=["python"])

    ceiling = compute_ceiling(
        jd, report=report, document_texts=["x"], master=master, aliases={}
    )

    assert ceiling["sub_scores"]["keywords"]["ceiling"] == 1.0
    assert ceiling["sub_scores"]["keywords"]["confidence"] == EXACT


def test_a_keyword_the_user_does_not_hold_does_not_raise_the_score():
    jd = StructuredJD(title="X", must_have=["python"])
    report = _report(sub_scores={"keywords": _sub(0.0)})

    ceiling = compute_ceiling(
        jd, report=report, document_texts=["x"], master=_master(), aliases={}
    )

    assert ceiling["sub_scores"]["keywords"]["ceiling"] == 0.0


# --- Title (0.20) -----------------------------------------------------------------


def test_the_title_ceiling_is_the_best_held_role_title():
    jd = StructuredJD(title="Senior Data Scientist")
    report = _report(sub_scores={"title": _sub(0.0)})
    master = _master(roles=[_role("r1", title_es="Data Scientist")])

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=master, aliases={}
    )

    assert ceiling["sub_scores"]["title"]["ceiling"] == pytest.approx(2 / 3, abs=1e-4)
    assert ceiling["sub_scores"]["title"]["confidence"] == EXACT


def test_a_headline_that_copies_the_posting_title_gains_nothing():
    """A2: a headline counts only through words a held role title also has."""
    jd = StructuredJD(title="Data Scientist")
    report = _report(sub_scores={"title": _sub(0.1)})
    master = _master(roles=[_role("r1", title_es="Analista")], headlines=["Data Scientist"])

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=master, aliases={}
    )

    assert ceiling["sub_scores"]["title"]["ceiling"] == 0.1, "the copy gains nothing"


def test_a_headline_sharing_a_word_with_a_held_title_counts_it():
    jd = StructuredJD(title="Machine Learning Engineer")
    report = _report(sub_scores={"title": _sub(0.0)})
    master = _master(
        roles=[_role("r1", title_es="Machine Learning Engineer")],
        headlines=["Senior Machine Learning Engineer"],
    )

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=master, aliases={}
    )

    assert ceiling["sub_scores"]["title"]["ceiling"] == 1.0


# --- Skills (0.40) ----------------------------------------------------------------


def _grade(requirement, level, *, must_have=True, basis="none"):
    return {
        "requirement": requirement,
        "must_have": must_have,
        "level": level,
        "basis": basis,
    }


def test_a_requirement_below_two_is_lifted_by_a_tagged_bullet():
    jd = StructuredJD(title="X", must_have=["python"])
    report = _report(
        grades=[_grade("python", 0)],
        sub_scores={"skills": _sub(0.0)},
    )
    master = _master(bullets=[_bullet("b1", "r1", skills=("python",))])

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=master, aliases={}
    )

    assert ceiling["sub_scores"]["skills"]["ceiling"] == pytest.approx(2 / 3, abs=1e-4)
    assert ceiling["sub_scores"]["skills"]["confidence"] == "estimate"


def test_a_family_sibling_tag_lifts_as_an_equivalent():
    jd = StructuredJD(title="X", must_have=["power bi"])
    report = _report(grades=[_grade("power bi", 0)], sub_scores={"skills": _sub(0.0)})
    master = _master(
        bullets=[_bullet("b1", "r1", skills=("tableau",))],
        families={"tableau": "bi", "power bi": "bi"},
    )

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=master, aliases={}
    )

    # level 2, equivalent (0.75 credit) over a must-have alone.
    assert ceiling["sub_scores"]["skills"]["ceiling"] == pytest.approx(0.5, abs=1e-4)


def test_a_grade_already_at_two_or_more_stays_where_it_is():
    jd = StructuredJD(title="X")
    report = _report(
        grades=[_grade("sql", 3, basis="direct"), _grade("python", 0)],
        sub_scores={"skills": _sub(0.0)},
    )

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=_master(), aliases={}
    )

    # sql stays at 3; python has no tag anywhere and stays at 0.
    assert ceiling["sub_scores"]["skills"]["ceiling"] == pytest.approx(0.5, abs=1e-4)


def test_an_unreachable_requirement_names_the_points_out_of_the_total():
    jd = StructuredJD(title="X", must_have=["python"])
    report = _report(grades=[_grade("python", 0)], sub_scores={"skills": _sub(0.0)})

    ceiling = compute_ceiling(
        jd, report=report, document_texts=[], master=_master(), aliases={}
    )

    rows = ceiling["unreachable"]["requirements"]
    assert [row["requirement"] for row in rows] == ["python"]
    # share 1.0 × (2−0)/3 × direct credit × Skills' 0.40 weight × 100.
    assert rows[0]["points"] == pytest.approx(26.67, abs=0.01)
    assert ceiling["unreachable"]["points"] == 100 - ceiling["high"]


# --- Experience (0.25) ------------------------------------------------------------


def _experience_case(*, off_track_tag: bool):
    jd = StructuredJD(title="X", years_required=6)
    report = _report(
        grades=[{**_grade("python", 2, basis="direct"), "bullet_id": "b1"}],
        sub_scores={"experience": _sub(0.25, detail={})},
    )
    master = _master(
        bullets=[
            _bullet("b1", "r1", skills=("python",)),
            _bullet("b2", "r2", skills=("python",) if off_track_tag else ()),
        ],
        roles=[
            _role("r1", start=date(2018, 1, 1), end=date(2021, 1, 1), bullet_ids=("b1",)),
            _role("r2", start=date(2021, 1, 1), end=date(2024, 1, 1), bullet_ids=("b2",)),
        ],
    )
    return jd, report, master


def test_an_off_track_role_with_a_tagged_bullet_becomes_relevant():
    jd, report, master = _experience_case(off_track_tag=True)

    ceiling = compute_ceiling(
        jd,
        report=report,
        document_texts=[],
        master=master,
        aliases={},
        today=date(2024, 1, 1),
    )

    assert ceiling["sub_scores"]["experience"]["ceiling"] == 1.0, "six relevant years"
    assert ceiling["sub_scores"]["experience"]["confidence"] == "estimate"


def test_an_off_track_role_without_a_matching_tag_stays_out():
    jd, report, master = _experience_case(off_track_tag=False)

    ceiling = compute_ceiling(
        jd,
        report=report,
        document_texts=[],
        master=master,
        aliases={},
        today=date(2024, 1, 1),
    )

    assert ceiling["sub_scores"]["experience"]["ceiling"] == 0.25, "three years of six"


# --- The whole function -----------------------------------------------------------


def test_the_fingerprint_moves_when_the_master_does():
    jd = StructuredJD(title="X")
    report = _report(sub_scores={"keywords": _sub(0.0)})

    first = compute_ceiling(
        jd, report=report, document_texts=[], master=_master(pool=["python"]), aliases={}
    )
    second = compute_ceiling(
        jd, report=report, document_texts=[], master=_master(pool=["python", "sql"]), aliases={}
    )

    assert first["fingerprint"] != second["fingerprint"]
    assert first["fingerprint"].startswith("sha256:")


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def test_the_ceiling_is_deterministic_and_makes_no_model_call(session, career, provider):
    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track
    )
    master = master_data(career.first_profile.id, session, career.first_track)
    before = len(provider.calls)

    kwargs = {
        "report": analysis.report,
        "document_texts": [unit.text for unit in analysis.document],
        "master": master,
        "aliases": alias_map(session),
    }
    first = compute_ceiling(analysis.jd, **kwargs)
    second = compute_ceiling(analysis.jd, **kwargs)

    assert first == second, "same inputs, byte-identical output"
    assert len(provider.calls) == before, "the ceiling makes no model call"
    assert first["low"] == first["high"], "the high end waits for F7.4"
    assert first["high_basis"] == "pending_f7_4"
    assert first["weights_version"] == "w4"
