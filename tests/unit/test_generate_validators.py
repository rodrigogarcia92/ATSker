"""The three F7.3 validators (the N7 milestone).

Pure functions over handed-in sources: the vocabulary, the bullets and the grades are
built here so each rule is exercised on its own — a fabricated skill, an invented
metric, a citation from another profile, and the two false-failure directions
(accents, case). Prose is written lower-case where only a closure rule is under test,
because a capitalised tool name legitimately trips the literal rule as well.
"""

import json
from pathlib import Path

from src.generate.validators import (
    CLOSURE_MISSING,
    CLOSURE_UNEVIDENCED,
    LITERAL,
    PROVENANCE,
    Sources,
    unsupported_claims,
    validate,
)
from src.normalize.text import fold
from src.normalize.vocabulary import match_text
from src.vocabulary import seed_vocabulary, vocabulary_hash

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

    assert closed_texts(violations, CLOSURE_MISSING) == ["kubernetes"]
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
    assert closed_texts(violations, CLOSURE_MISSING) == ["tableau"]


def test_a_summary_skill_named_in_the_prose_must_be_evidenced_at_level_two():
    output = {
        "summary": {"text": "Analista con python y sql.", "cites": ["b1"]},
        "skills": ["python", "sql"],
    }
    grades = [{"level": 2, "evidence_id": "b1"}]

    violations = validate_summary(output, grades=grades)

    # SQL is in the pool, but no level >= 2 grade names a bullet that shows it.
    assert closed_texts(violations, CLOSURE_UNEVIDENCED) == ["sql"]
    assert closed_texts(violations, CLOSURE_MISSING) == []


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


# --- F.0: literal preservation compares tokens, never substrings -------------------


NUMBERED = Sources(
    bullets={"b1": "Reduje 30% el tiempo de reporte"},
    stories={},
    skills=frozenset(),
    aliases={},
)


def literal(text: str, *, source: Sources = NUMBERED) -> list[str]:
    output = {"text": text, "cites": ["b1"]}
    violations = validate(output, sources=source, profile_id="p", session=None, kind="bullet")
    return [violation.text for violation in violations if violation.rule == LITERAL]


def test_a_number_the_source_does_not_have_is_a_violation():
    """`3` is not `30%`: the old substring check let "3 meses" through (F.0)."""
    assert literal("Reduje en 3 meses el tiempo") == ["3"]


def test_a_number_the_source_has_passes():
    assert literal("Reduje el tiempo de reporte un 30%") == []


def test_a_number_matches_its_own_source_without_the_sign():
    assert literal("Reduje el tiempo un 30") == []


def test_a_word_prefix_is_not_a_match():
    base = Sources(bullets={"b1": "Trabajé en Banco Demo"}, aliases={})
    assert literal("Trabajé en Ban Andino", source=base) == ["Ban"]


def test_a_word_the_source_has_passes():
    base = Sources(bullets={"b1": "Trabajé en Banco Demo"}, aliases={})
    assert literal("Trabajé en Banco Demo", source=base) == []


# --- D3: F7.3 as written — the skills block needs the pool, the prose needs level 2 ----


def test_the_skills_block_needs_the_pool_and_no_level():
    """`python` is in the pool and graded below 2: fine in the list, the text names none."""
    output = {
        "summary": {"text": "Automaticé reportes de dirección.", "cites": ["b1"]},
        "skills": ["python"],
    }

    assert validate_summary(output, grades=[{"level": 1, "evidence_id": "b1"}]) == []


def test_a_skill_outside_the_pool_in_the_skills_block_is_one_missing_violation():
    output = {
        "summary": {"text": "Automaticé reportes de dirección.", "cites": ["b1"]},
        "skills": ["python", "tableau"],
    }

    violations = validate_summary(output, grades=[])

    assert [(v.rule, v.text) for v in violations] == [(CLOSURE_MISSING, "tableau")]


def test_prose_naming_a_pool_skill_without_a_level_two_citation_is_unevidenced():
    output = {
        "summary": {"text": "Automaticé reportes con python.", "cites": ["b1"]},
        "skills": [],
    }

    violations = validate_summary(output, grades=[{"level": 1, "evidence_id": "b1"}])

    assert [(v.rule, v.text) for v in violations] == [(CLOSURE_UNEVIDENCED, "python")]


CITED_ONLY = Sources(
    bullets={"b1": "Automaticé reportes de dirección", "b2": "Escribí scripts en Python"},
    skills=frozenset({"python"}),
    aliases=ALIASES,
)


def test_a_level_three_grade_on_a_cited_bullet_evidences_the_summary():
    output = {"summary": {"text": "Reportes con python.", "cites": ["b2"]}, "skills": []}

    violations = validate(
        output,
        sources=CITED_ONLY,
        profile_id="p",
        session=None,
        kind="summary",
        grades=[{"level": 3, "evidence_id": "b2"}],
    )

    assert violations == []


def test_a_grade_on_a_bullet_the_summary_does_not_cite_does_not_evidence_it():
    """F7.3: "in the selected bullets". b2 holds python at level 3, but b1 is what is cited."""
    output = {"summary": {"text": "Reportes con python.", "cites": ["b1"]}, "skills": []}

    violations = validate(
        output,
        sources=CITED_ONLY,
        profile_id="p",
        session=None,
        kind="summary",
        grades=[{"level": 3, "evidence_id": "b2"}],
    )

    assert [(v.rule, v.text) for v in violations] == [(CLOSURE_UNEVIDENCED, "python")]


def test_a_line_break_ends_a_sentence_like_a_full_stop():
    assert unsupported_claims("diseñé tableros\nApliqué reglas", "", {}) == []
    assert unsupported_claims("diseñé tableros y Apliqué reglas", "", {}) == ["Apliqué"]


def test_a_skill_missing_from_the_pool_is_reported_once_even_if_listed_and_named():
    output = {
        "summary": {"text": "Reportes en tableau.", "cites": ["b1"]},
        "skills": ["tableau"],
    }

    violations = validate_summary(output, grades=[])

    assert [(v.rule, v.text) for v in violations] == [(CLOSURE_MISSING, "tableau")]


HELD_TITLES = Sources(
    bullets={"b1": "Automaticé reportes de dirección"},
    skills=frozenset({"reporting"}),
    aliases={
        "reporting": "reporting",
        "teams": "microsoft teams",
        "microsoft teams": "microsoft teams",
    },
    titles=("Data Analyst",),
)


def test_a_summary_may_name_a_title_the_user_holds_and_ordinary_english_is_not_a_skill():
    output = {
        "summary": {
            "text": "Experienced Data Analyst with a background in reporting, working with teams",
            "cites": ["b1"],
        },
        "skills": [],
    }

    violations = validate(
        output, sources=HELD_TITLES, profile_id="p", session=None, kind="summary", grades=[]
    )

    assert LITERAL not in [v.rule for v in violations]
    assert "microsoft teams" not in [v.text for v in violations]
    assert [(v.rule, v.text) for v in violations] == [(CLOSURE_UNEVIDENCED, "reporting")]


def test_a_title_does_not_support_a_name_outside_it_or_a_number():
    output = {
        "summary": {"text": "Trabajé en Globex como Data Analyst 3 años", "cites": ["b1"]},
        "skills": [],
    }

    violations = validate(
        output, sources=HELD_TITLES, profile_id="p", session=None, kind="summary", grades=[]
    )

    assert [v.text for v in violations if v.rule == LITERAL] == ["Globex", "3"]


def test_a_bullet_proposal_inventing_a_proper_noun_is_still_a_literal_violation():
    output = {"text": "Automaticé reportes con Informatica en producción", "cites": ["b1"]}

    violations = validate(output, sources=sources(), profile_id="p", session=None, kind="bullet")

    assert [(v.rule, v.text) for v in violations] == [(LITERAL, "Informatica")]


def test_ambiguous_aliases_are_skipped_only_when_asked():
    aliases = {"teams": "microsoft teams", "word": "microsoft word", "go": "go", "sql": "sql"}

    assert match_text("worked with teams", aliases) == ["microsoft teams"], "scoring is unchanged"
    assert match_text("worked with teams", aliases, skip_ambiguous=True) == []
    assert match_text("open the word file, then go", aliases, skip_ambiguous=True) == []
    assert match_text("sql and teams", aliases, skip_ambiguous=True) == ["sql"]


def test_the_vocabulary_hash_is_unchanged_by_the_ambiguous_alias_list(session):
    """The list is code-side data: the seed, and so the frozen w4 hash, is untouched."""
    seed = Path(__file__).resolve().parents[2] / "src" / "normalize" / "skills_seed.json"
    seed_vocabulary(session, json.loads(seed.read_text(encoding="utf-8")))

    assert vocabulary_hash(session) == (
        "sha256:2323925e0fcbc416d368920a15aa4fee4c38c3e1e2f743d4be4abcaf1ca71c73"
    )
    listed = json.loads((seed.parent / "ambiguous_aliases.json").read_text(encoding="utf-8"))
    assert listed == ["teams", "word", "go"]
    assert all(fold(alias) == alias for alias in listed)
