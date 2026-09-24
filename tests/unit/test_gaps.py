"""N5 gap analysis (PRD F6, F6.1): detection bands, honest verdicts, one call.

Detection is deterministic and free — `src/score/gaps.py` is inside the boundary
test's no-network sweep, and these tests feed it gradings directly. The
interpretation call is tested against a stub: it may explain the gaps it was given
and never grow, shrink or reorder the list.
"""

import json

import pytest

from src.extract import client as extract_client
from src.extract.gaps import GapInput, GapViolation, interpret_gaps
from src.jd import StructuredJD
from src.score.gaps import Disqualifier, Graded, detect_gaps, disqualifier_verdicts
from tests.conftest import login

JD = StructuredJD(must_have=["airflow", "sql"], nice_to_have=["pandas", "inglés", "stata"])

GAP_ANSWER = json.dumps(
    {
        "gaps": [
            {
                "requirement": "airflow",
                "blocking": True,
                "interpretation": "Sin orquestación no hay pipeline que defender en la entrevista.",
            },
            {
                "requirement": "sql",
                "blocking": False,
                "interpretation": "SQL está mencionado, no demostrado con un resultado.",
            },
        ],
        "warning": {
            "text": "Salto del sector público",
            "handling": "Encuádralo como transferencia de método, no como cambio de sector.",
        },
        "not_found": "No había historias disponibles para este análisis.",
    }
)


class Provider:
    """One canned answer per schema name, priced like a real call."""

    def __init__(self, answers: dict[str, str]):
        self.calls: list[dict] = []
        self.answers = answers

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        return {
            "choices": [{"message": {"content": self.answers[name]}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 120, "cost": "0.000123"},
        }


@pytest.fixture
def provider(monkeypatch, test_settings):
    stub = Provider({"GapInterpretation": GAP_ANSWER})
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def test_detection_emits_levels_zero_and_one_in_f6_ones_band_order():
    """Must-0, must-1, nice-0, nice-1; within a band, the order the JD stated them in."""
    graded = [
        Graded("excel", 2, False),
        Graded("sql", 1, True, bullet_id="b1", bullet_text="Consultas en SQL"),
        Graded("stata", 0, False),
        Graded("python", 3, True),
        Graded("airflow", 0, True),
        Graded("pandas", 1, False, bullet_id="b2", bullet_text="Análisis con pandas"),
        Graded("inglés", 1, False, bullet_id="b3", bullet_text="Reportes en inglés"),
    ]

    gaps = detect_gaps(
        graded,
        must_have=JD.must_have,
        nice_to_have=JD.nice_to_have,
    )

    assert [(gap.requirement, gap.level, gap.must_have) for gap in gaps] == [
        ("airflow", 0, True),
        ("sql", 1, True),
        ("stata", 0, False),
        ("pandas", 1, False),
        ("inglés", 1, False),
    ]
    assert [(gap.bullet_id, gap.bullet_text) for gap in gaps] == [
        (None, None),
        ("b1", "Consultas en SQL"),
        (None, None),
        ("b2", "Análisis con pandas"),
        ("b3", "Reportes en inglés"),
    ], "a bullet came close only at level 1, with its snapshotted text"


def test_a_transfer_covered_must_have_lands_in_the_fifth_band_after_the_four():
    """F6.1: not a gap in the score's sense — the claim most likely to be
    questioned, listed with its reason so the argument can be prepared."""
    graded = [
        Graded("airflow", 0, True),
        Graded("excel", 1, False, bullet_id="b0", bullet_text="Uso Excel a diario"),
        Graded(
            "power bi",
            3,
            True,
            basis="equivalent",
            transfer_reason="Tableau hace el mismo trabajo.",
        ),
    ]

    gaps = detect_gaps(graded, must_have=JD.must_have, nice_to_have=JD.nice_to_have)

    assert [(gap.requirement, gap.covered_by_transfer) for gap in gaps] == [
        ("airflow", False),
        ("excel", False),
        ("power bi", True),
    ], "the fifth band comes after the four, not inside them"
    covered = gaps[-1]
    assert covered.level == 3 and covered.must_have is True
    assert covered.transfer_reason == "Tableau hace el mismo trabajo."
    assert covered.bullet_text is None
    assert all(not gap.covered_by_transfer for gap in gaps[:-1])


def test_a_direct_requirement_at_level_three_is_no_gap_and_no_band():
    graded = [Graded("python", 3, True, basis="direct")]

    assert detect_gaps(graded, must_have=["python"], nice_to_have=[]) == []


def test_a_degree_requirement_is_met_or_unmet_by_the_education_rows():
    assert disqualifier_verdicts(["título universitario"], has_education=True) == [
        Disqualifier("título universitario", "met")
    ]
    assert disqualifier_verdicts(["título universitario"], has_education=False) == [
        Disqualifier("título universitario", "unmet")
    ]
    assert disqualifier_verdicts(["degree_required"], has_education=False) == [
        Disqualifier("degree_required", "unmet")
    ], "the slug form is the same ask"


def test_requirements_atsker_cannot_check_stay_unverified():
    verdicts = disqualifier_verdicts(
        ["Presencial en Lima", "Autorización de trabajo en la UE", "Licencia de conducir"],
        has_education=True,
    )

    assert verdicts == [
        Disqualifier("Presencial en Lima", "unverified"),
        Disqualifier("Autorización de trabajo en la UE", "unverified"),
        Disqualifier("Licencia de conducir", "unverified"),
    ], "no field answers a city, an authorisation or a licence — never a guess"


def test_the_interpretation_keeps_the_gaps_in_the_order_given(session, provider):
    gaps = [
        GapInput("airflow", 0, True),
        GapInput("sql", 1, True, bullet_text="Consultas en SQL"),
    ]

    reading = interpret_gaps(
        session,
        gaps,
        JD,
        standing_risks=["salir del sector público"],
        stories=[],
        language="es",
    )

    assert [note.requirement for note in reading.notes] == ["airflow", "sql"]
    assert [note.blocking for note in reading.notes] == [True, False]
    assert reading.warning.text == "Salto del sector público"
    assert reading.warning.handling.startswith("Encuádralo")
    assert len(reading.calls) == 1


def test_a_gap_the_model_invented_fails_loudly_after_one_retry(session, monkeypatch, test_settings):
    invented = json.dumps(
        {
            "gaps": [{"requirement": "excel", "blocking": False, "interpretation": "no aplica"}],
            "warning": {"text": "", "handling": ""},
            "not_found": "",
        }
    )
    stub = Provider({"GapInterpretation": invented})
    monkeypatch.setattr(extract_client, "_post", stub)

    with pytest.raises(GapViolation):
        interpret_gaps(session, [GapInput("airflow", 0, True)], JD)

    assert len(stub.calls) == 2, "one retry, then fail loudly (F5.4's citation rule)"


def test_an_empty_story_table_still_yields_an_answer_and_the_output_says_so(session, provider):
    reading = interpret_gaps(
        session,
        [GapInput("airflow", 0, True), GapInput("sql", 1, True, bullet_text="Consultas en SQL")],
        JD,
        stories=[],
        language="es",
    )

    assert [note.requirement for note in reading.notes] == ["airflow", "sql"], "the answer came"
    prompt = provider.calls[0]["messages"][1]["content"]
    assert "(none available)" in prompt, "the model is told the table was empty"
    assert reading.not_found == "No había historias disponibles para este análisis."


def test_the_profile_page_edits_standing_risks(client, session, career):
    """F6.1's §3.5: without this editor the gap analysis reads an empty array forever."""
    login(client, career.first.email)

    assert "Riesgos persistentes" in client.get("/profile").text

    saved = client.post(
        "/profile",
        data={
            "display_name": "Ana",
            "headline": "",
            "summary": "",
            "standing_risks": (
                "salir del sector público\nbrecha de seniority\nsalir del sector público"
            ),
        },
        follow_redirects=False,
    )

    assert saved.status_code == 303
    session.expire_all()
    assert career.first_profile.standing_risks == [
        "salir del sector público",
        "brecha de seniority",
    ], "one per line, without duplicates"
    page = client.get("/profile").text
    assert "salir del sector público" in page and "brecha de seniority" in page

    client.post("/profile", data={"display_name": "Ana", "standing_risks": ""})
    session.expire_all()
    assert career.first_profile.standing_risks == [], "clearing the field empties the array"
