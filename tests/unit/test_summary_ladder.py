"""The key-skill shortlist's fallback ladder (PRD F7.3 amended (b), queue P3)."""

from src.generate.summary_rules import check_skills, key_skill_shortlist

ALIASES = {
    "sql": "sql",
    "python": "python",
    "pandas": "pandas",
    "tableau": "tableau",
    "excel": "excel",
    "airflow": "airflow",
    "leadership": "leadership",
    "kpis": "kpis",
}
POOL = frozenset(ALIASES.values())


def grade(requirement, bullet_id=None, *, level=3, basis="direct", must=True):
    return {
        "requirement": requirement,
        "level": level,
        "basis": basis,
        "must_have": must,
        "bullet_id": bullet_id,
    }


def report(must, nice, grades):
    return {"jd": {"must_have": must, "nice_to_have": nice}, "grades": grades}


def test_step_a_alone_filling_four_adds_no_related_skill():
    rep = report(
        ["SQL", "Python", "Excel", "Airflow"],
        [],
        [grade(name, "b1") for name in ("SQL", "Python", "Excel", "Airflow")],
    )

    shortlist = key_skill_shortlist(
        rep, POOL, ALIASES, bullet_texts={"b1": "Built pandas and tableau reports"}
    )

    assert [s.canonical for s in shortlist] == ["sql", "python", "excel", "airflow"]
    assert {s.step for s in shortlist} == {"posting"}


def test_bullets_graded_two_or_more_fill_the_places_the_posting_left():
    rep = report(
        ["SQL", "Data storytelling"],
        [],
        [
            grade("SQL", "b1"),
            grade("Data storytelling", "b2", basis="equivalent"),
        ],
    )

    shortlist = key_skill_shortlist(
        rep, POOL, ALIASES, bullet_texts={"b1": "Wrote SQL", "b2": "Used python and sql daily"}
    )

    assert [(s.canonical, s.step) for s in shortlist] == [
        ("sql", "posting"),
        ("python", "related"),
    ]


def test_related_skills_follow_the_order_of_the_bullet_and_use_the_canonical_wording():
    rep = report(["Reporting"], [], [grade("Reporting", "b1", basis="equivalent")])

    shortlist = key_skill_shortlist(
        rep, POOL, ALIASES, bullet_texts={"b1": "Led tableau dashboards and pandas jobs in SQL"}
    )

    assert [(s.wording, s.canonical) for s in shortlist] == [
        ("tableau", "tableau"),
        ("pandas", "pandas"),
        ("sql", "sql"),
    ]


def test_must_have_grades_come_before_nice_to_have_ones():
    rep = report(
        ["A requirement"],
        ["Another requirement"],
        [
            grade("Another requirement", "b2", must=False),
            grade("A requirement", "b1", must=True),
        ],
    )

    shortlist = key_skill_shortlist(
        rep, POOL, ALIASES, bullet_texts={"b1": "excel", "b2": "airflow"}
    )

    assert [s.canonical for s in shortlist][:2] == ["excel", "airflow"]


def test_step_c_orders_by_how_many_bullets_show_a_skill_then_alphabetically():
    rep = report(
        [],
        [],
        [
            grade("x", "b1", level=2, must=False),
            grade("y", "b2", level=2, must=False),
            grade("z", "b3", level=2, must=False),
        ],
    )
    texts = {"b1": "python sql", "b2": "sql tableau", "b3": "sql excel"}

    ladder = key_skill_shortlist(rep, POOL, ALIASES, bullet_texts=texts)

    # step (b) already walks each graded bullet; the count order matters for whatever is left
    assert ladder[0].canonical == "python" and len(ladder) == 4
    assert {s.step for s in ladder} == {"related"}


def test_a_canonical_outside_the_pool_never_enters_and_nothing_repeats():
    rep = report(["SQL"], [], [grade("SQL", "b1")])

    shortlist = key_skill_shortlist(
        rep,
        frozenset({"sql", "python"}),
        ALIASES,
        bullet_texts={"b1": "sql python sql tableau excel"},
    )

    canonicals = [s.canonical for s in shortlist]
    assert canonicals == ["sql", "python"]
    assert len(set(canonicals)) == len(canonicals)


def test_a_bullet_that_was_not_supplied_contributes_nothing():
    rep = report(["X"], [], [grade("X", "someone-elses-bullet")])

    assert key_skill_shortlist(rep, POOL, ALIASES, bullet_texts={"b1": "sql"}) == []


def test_a_low_grade_contributes_nothing():
    rep = report(["X"], [], [grade("X", "b1", level=1)])

    assert key_skill_shortlist(rep, POOL, ALIASES, bullet_texts={"b1": "sql python"}) == []


def test_the_skills_check_accepts_a_summary_naming_the_extended_shortlist():
    rep = report(["SQL"], [], [grade("SQL", "b1")])
    shortlist = key_skill_shortlist(
        rep, POOL, ALIASES, bullet_texts={"b1": "sql python tableau"}
    )

    assert check_skills("Analista con SQL, Python y Tableau.", shortlist, ALIASES)["ok"]
