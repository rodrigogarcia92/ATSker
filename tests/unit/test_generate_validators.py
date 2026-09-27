"""The three F7.3 validators (the N7 milestone).

Pure functions over handed-in sources: the vocabulary, the bullets and the grades are
built here so each rule is exercised on its own — a fabricated skill, an invented
metric, a citation from another profile, and the two false-failure directions
(accents, case). Prose is written lower-case where only a closure rule is under test,
because a capitalised tool name legitimately trips the literal rule as well.
"""

from src.generate.validators import CLOSURE, LITERAL, PROVENANCE, Sources, validate

ALIASES = {
    "python": "python",
    "power bi": "power bi",
    "tableau": "tableau",
    "kubernetes": "kubernetes",
    "sql": "sql",
}


def sources(**overrides) -> Sources:
    base = {
        "bullets": {"b1": "Automaticé el reporte con Python y Power BI"},
        "stories": {"s1": "Llevé el reporte manual a un proceso que bajó el cierre un 30%."},
        "roles": {"r1": "Analista de datos"},
        "skills": frozenset({"python", "power bi", "sql"}),
        "aliases": ALIASES,
    }
    base.update(overrides)
    return Sources(**base)


def validate_summary(output, **kwargs):
    return validate(
        output, sources=sources(), profile_id="p", session=None, kind="summary", **kwargs
    )


def closed_texts(violations, rule):
    return [violation.text for violation in violations if violation.rule == rule]


def test_a_fabricated_skill_is_rejected():
    output = {
        "summary": {"text": "Analista con python y kubernetes en producción.", "cites": ["b1"]},
        "skills": ["python", "kubernetes"],
    }

    violations = validate_summary(output, grades=[{"level": 3, "evidence_id": "b1"}])

    assert closed_texts(violations, CLOSURE) == ["kubernetes"]
    assert PROVENANCE not in [violation.rule for violation in violations], "the citation is fine"


def test_a_story_bullet_with_an_invented_metric_fails_literal_preservation():
    output = {
        "bullets": [
            {
                "text": "Reduje el cierre un 40% llevando el reporte a un proceso automático.",
                "story_id": "s1",
                "role_id": "r1",
            }
        ]
    }

    violations = validate(
        output, sources=sources(), profile_id="p", session=None, kind="story_bullets"
    )

    assert [violation.rule for violation in violations] == [LITERAL]
    assert violations[0].text == "40%"
    start, end = violations[0].span
    assert output["bullets"][0]["text"][start:end] == "40%"


def test_a_citation_of_another_profile_fails_provenance():
    output = {
        "summary": {"text": "automaticé reportes.", "cites": ["someone-elses-bullet"]},
        "skills": [],
    }

    violations = validate_summary(output)

    assert [violation.rule for violation in violations] == [PROVENANCE]
    assert "someone-elses-bullet" in violations[0].message


def test_an_item_without_a_citation_fails_provenance():
    output = {"text": "automaticé el reporte de dirección", "cites": []}

    violations = validate(output, sources=sources(), profile_id="p", session=None, kind="bullet")

    assert [violation.rule for violation in violations] == [PROVENANCE]


def test_an_equivalent_tool_cannot_be_named_in_a_summary():
    """F7.3 rule 3: a tool the user does not have is a gap, never a sentence — even
    when the vocabulary calls its sibling equivalent."""
    output = {
        "summary": {"text": "tableros en power bi y tableau para dirección.", "cites": ["b1"]},
        "skills": ["power bi", "tableau"],
    }
    grades = [{"level": 3, "evidence_id": "b1"}]

    violations = validate_summary(output, grades=grades)

    assert violations, "tableau is not in the user's data"
    assert closed_texts(violations, CLOSURE) == ["tableau"]


def test_a_summary_skill_must_be_evidenced_at_level_two():
    output = {
        "summary": {"text": "Analista con python y sql.", "cites": ["b1"]},
        "skills": ["python", "sql"],
    }
    grades = [{"level": 2, "evidence_id": "b1"}]

    violations = validate_summary(output, grades=grades)

    # SQL is in the pool, but no level >= 2 grade names a bullet that shows it.
    assert closed_texts(violations, CLOSURE) == ["sql"]


def test_accents_and_case_do_not_cause_false_failures():
    base = sources(
        bullets={"b1": "Diseñé el modelo de riesgo con Python"},
        stories={},
    )
    output = {"text": "disene el modelo de riesgo con python", "cites": ["b1"]}

    violations = validate(output, sources=base, profile_id="p", session=None, kind="bullet")

    assert violations == []


def test_a_proper_noun_the_sources_do_not_have_is_a_violation():
    output = {"text": "Migré el sistema a Globex en 2024", "cites": ["b1"]}

    violations = validate(output, sources=sources(), profile_id="p", session=None, kind="bullet")

    assert [violation.rule for violation in violations] == [LITERAL, LITERAL]
    assert [violation.text for violation in violations] == ["Globex", "2024"]


def test_a_sentence_starting_capital_is_not_a_proper_noun():
    output = {"text": "Los tableros que mantuve", "cites": ["b1"]}

    violations = validate(output, sources=sources(), profile_id="p", session=None, kind="bullet")

    assert LITERAL not in [violation.rule for violation in violations]


def test_a_clean_output_passes_every_rule():
    output = {
        "summary": {"text": "Automaticé el reporte con Python y Power BI.", "cites": ["b1"]},
        "skills": ["python", "power bi"],
    }
    grades = [{"level": 3, "evidence_id": "b1"}]

    assert validate_summary(output, grades=grades) == []
