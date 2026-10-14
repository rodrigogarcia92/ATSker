"""summary_v5: base skills are the user's own, and the retry answers the validators (queue P4)."""

from types import SimpleNamespace

from src.extract.generation import Proposal
from src.extract.prompts import SUMMARY_V4, SUMMARY_V5
from src.generate.summary_rules import KeySkill, propose_summary, violation_instruction
from src.generate.validators import (
    CLOSURE_MISSING,
    CLOSURE_UNEVIDENCED,
    LITERAL,
    PROVENANCE,
    Sources,
    Violation,
    validate,
)
from src.jd import StructuredJD

ALIASES = {
    "python": "python",
    "sql": "sql",
    "leadership": "leadership",
    "kpis": "kpis",
    "reporting": "reporting",
}
BASE_TEXT = "Analista de datos con liderazgo, leadership y kpis."


def sources(**overrides) -> Sources:
    values = {
        "bullets": {"b1": "Automaticé el reporte con python y sql"},
        "summaries": {"base1": BASE_TEXT},
        "skills": frozenset({"python", "sql", "leadership", "kpis"}),
        "aliases": ALIASES,
    }
    values.update(overrides)
    return Sources(**values)


GRADES = [{"level": 3, "evidence_id": "b1"}]


def check(text, cites, **overrides):
    return validate(
        {"summary": {"text": text, "cites": cites}},
        sources=sources(**overrides),
        profile_id="p",
        session=None,
        kind="summary",
        grades=GRADES,
    )


# --- the validator ------------------------------------------------------------------


def test_a_skill_the_cited_base_names_counts_as_evidenced():
    violations = check("Uso python, leadership y kpis.", ["b1", "summary:base1"])

    assert [v for v in violations if v.rule == CLOSURE_UNEVIDENCED] == []


def test_the_same_answer_not_citing_the_base_is_unevidenced_as_before():
    violations = check("Uso python, leadership y kpis.", ["b1"])

    assert {v.text for v in violations if v.rule == CLOSURE_UNEVIDENCED} == {"leadership", "kpis"}


def test_a_skill_outside_the_pool_still_fails_even_when_the_base_names_it():
    violations = check(
        "Uso python y reporting.",
        ["b1", "summary:base1"],
        summaries={"base1": "Analista con reporting."},
    )

    assert [v.text for v in violations if v.rule == CLOSURE_MISSING] == ["reporting"]


def test_other_kinds_are_unchanged():
    uncited = {"text": "Uso leadership.", "cites": []}
    cited = {"text": "Uso leadership.", "cites": ["b1"]}

    def run(output):
        return validate(
            output, sources=sources(), profile_id="p", session=None, kind="bullet", grades=GRADES
        )

    assert [v.rule for v in run(uncited)] == [PROVENANCE]
    assert run(cited) == [], "a bullet's skills only have to be in the pool, as before"


# --- the prompt ---------------------------------------------------------------------


def test_v5_adds_the_two_sentences_and_v4_stays_as_it_was():
    assert SUMMARY_V5.version == "summary_v5" and SUMMARY_V4.version == "summary_v4"
    assert "Cite the bullet that shows each skill you name." in SUMMARY_V5.system
    assert "is not a fact to keep: drop it, or replace it with a shortlist skill" in (
        SUMMARY_V5.system
    )
    assert "Cite the bullet that shows" not in SUMMARY_V4.system
    assert "Never return a list of skills" in SUMMARY_V5.system


# --- the retry ----------------------------------------------------------------------

JD = StructuredJD(title="Analista de datos")
SHORTLIST = [KeySkill("python", "python"), KeySkill("sql", "sql"), KeySkill("kpis", "kpis")]
# Inside `summary_v6`'s 60-100 words, so a "clean" answer is clean under the current rules.
CLEAN = (
    "Analista de datos con python, sql y kpis. Durante cinco años trabajé junto a equipos "
    "de negocio para convertir sus preguntas en informes que se leen rápido y decisiones "
    "que se toman a tiempo. Reduje el tiempo del reporte mensual y dejé el proceso en manos "
    "de quien lo usa cada día. Cuidé la calidad de los números antes de publicarlos y "
    "expliqué cada resultado en una frase. Busco un puesto donde medir y contar lo que "
    "dicen los datos sea parte del trabajo de cada semana."
)


def proposal(text, cites=("b1",)):
    return Proposal(
        kind="summary",
        output={"summary": {"text": text, "cites": list(cites)}},
        completion=SimpleNamespace(),
    )


class Fake:
    def __init__(self, *texts):
        self.texts = list(texts)
        self.retries: list = []
        self.shortlist: list = []

    def __call__(self, session, **kwargs):
        self.retries.append(kwargs["retry"])
        self.shortlist = kwargs["shortlist"]
        return proposal(self.texts[len(self.retries) - 1])


def run(fake, validator):
    return propose_summary(
        None,
        jd=JD,
        bullets=[],
        track_skills=[],
        pool=[],
        grades=[],
        language="es",
        title="Analista de datos",
        base=None,
        shortlist=SHORTLIST,
        aliases=ALIASES,
        banned=[],
        validate=validator,
        call=fake,
    )


def finding_for(word):
    def validator(output):
        if word in output["summary"]["text"]:
            return [Violation(CLOSURE_UNEVIDENCED, "summary", word, "x")]
        return []

    return validator


def test_a_clean_first_answer_makes_one_call():
    fake = Fake(CLEAN)

    chosen, checklist, violations = run(fake, lambda output: [])

    assert len(fake.retries) == 1 and violations == [] and all(r["ok"] for r in checklist)
    assert chosen.output["summary"]["text"] == CLEAN


def test_a_validator_finding_alone_triggers_the_retry_with_the_instruction():
    fake = Fake(CLEAN + " Más kpis", CLEAN)

    chosen, _checklist, violations = run(fake, finding_for("Más kpis"))

    assert len(fake.retries) == 2
    previous, instructions = fake.retries[1]
    assert "Más kpis" in previous
    assert instructions == ["remove «Más kpis»: no cited bullet shows it"]
    assert violations == [] and chosen.output["summary"]["text"] == CLEAN


def test_the_answer_without_findings_wins_even_with_fewer_style_rules():
    # First: every style rule passes but it has a finding. Second: no finding, the title fails.
    fake = Fake(CLEAN + " ZZ", "Trabajo con python, sql y kpis.")

    chosen, checklist, violations = run(fake, finding_for("ZZ"))

    assert violations == []
    assert chosen.output["summary"]["text"] == "Trabajo con python, sql y kpis."
    assert not checklist[0]["ok"], "the title rule fails on the chosen answer"


def test_with_findings_on_both_the_one_passing_more_style_rules_wins():
    fake = Fake("Trabajo con python, sql y kpis. ZZ", CLEAN + " ZZ")

    chosen, _checklist, violations = run(fake, finding_for("ZZ"))

    assert len(fake.retries) == 2
    assert chosen.output["summary"]["text"] == CLEAN + " ZZ"
    assert violations


def test_the_first_answer_wins_when_the_retry_is_worse_on_style_and_both_have_findings():
    fake = Fake(CLEAN + " ZZ", "Trabajo con python, sql y kpis. ZZ")

    chosen, _checklist, _violations = run(fake, finding_for("ZZ"))

    assert chosen.output["summary"]["text"] == CLEAN + " ZZ"


def test_a_tie_keeps_the_second_and_there_are_never_three_calls():
    fake = Fake("Uno ZZ", "Dos ZZ", "Tres ZZ")

    chosen, _checklist, _violations = run(fake, finding_for("ZZ"))

    assert len(fake.retries) == 2
    assert chosen.output["summary"]["text"] == "Dos ZZ"


def test_the_retry_names_failed_style_rules_and_every_finding_once():
    fake = Fake("Texto sin título ZZ ZZ", CLEAN)

    run(fake, finding_for("ZZ"))

    _previous, instructions = fake.retries[1]
    assert instructions[0].startswith("the first sentence must open with the career title")
    assert instructions.count("remove «ZZ»: no cited bullet shows it") == 1


def test_the_shortlist_rows_carry_their_step():
    fake = Fake(CLEAN)

    run(fake, lambda output: [])

    assert fake.shortlist[0] == ("python", "python", "posting")


def test_the_exact_instruction_texts():
    assert violation_instruction(Violation(CLOSURE_UNEVIDENCED, "s", "kpis", "")) == (
        "remove «kpis»: no cited bullet shows it"
    )
    assert violation_instruction(Violation(CLOSURE_MISSING, "s", "kpis", "")) == (
        "remove «kpis»: no cited bullet shows it"
    )
    assert violation_instruction(Violation(LITERAL, "s", "30%", "")) == (
        "remove «30%»: it is not in the sources you cite"
    )
    assert violation_instruction(Violation(PROVENANCE, "s", "zzz", "")) == (
        "cite only ids that were given"
    )
