"""Evidence grading: citation integrity, one retry, and the coverage arithmetic.

The citation rules are the anti-fabrication guarantee at this layer: a level above
zero must name a bullet the profile actually has, and no requirement may be silently
left ungraded.
"""

import json
import uuid

import pytest

from src.extract.client import CallOptions, StructuredOutputError
from src.extract.grading import (
    PURPOSE,
    CitationViolation,
    EvidenceReport,
    grade_evidence,
    requirements_of,
)
from src.jd import StructuredJD
from src.models import LlmCall, Skill
from src.score.evidence import Level, evidence_coverage
from src.score.weights import W3


def jd() -> StructuredJD:
    return StructuredJD(
        title="Data Analyst",
        must_have=["python", "sql"],
        nice_to_have=["power bi"],
    )


class Bullets:
    """Stands in for ORM bullets: grading reads id, text and the skill chips."""

    def __init__(self) -> None:
        self.ids = [uuid.uuid4() for _ in range(2)]
        self.texts = [
            "Automaticé el reporte mensual con Python y reduje 30% el tiempo de cierre",
            "Mantuve tableros de Power BI para 40 usuarios",
        ]

    def __iter__(self):
        for identifier, text in zip(self.ids, self.texts, strict=True):
            yield type(
                "B", (), {"id": identifier, "text_es": text, "text_en": None, "skills": []}
            )()


@pytest.fixture
def bullets() -> Bullets:
    return Bullets()


def grading_payload(bullets: Bullets, levels=(2, 1, 3)) -> str:
    ids = [str(bullets.ids[0]), str(bullets.ids[1]), str(bullets.ids[1])]
    return json.dumps(
        {
            "grades": [
                {
                    "index": index,
                    "level": level,
                    "basis": "none" if level == 0 else "direct",
                    "source": None if level == 0 else "bullet",
                    "evidence_id": (None if level == 0 else ids[index]),
                    "transfer_reason": None,
                }
                for index, level in enumerate(levels)
            ],
            "note": "sql solo aparece en una lista",
        }
    )


def stub(monkeypatch, payloads: list[str]) -> list[dict]:
    from src.extract import client

    seen: list[dict] = []
    queue = list(payloads)

    def fake_post(body, api_key):
        seen.append(body)
        content = queue[min(len(seen) - 1, len(queue) - 1)]
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 900, "completion_tokens": 120, "cost": "0.00005"},
        }

    monkeypatch.setattr(client, "_post", fake_post)
    return seen


def test_grades_come_back_with_their_citations(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])

    report = grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert [(entry.requirement, entry.level) for entry in report.levels] == [
        ("python", 2),
        ("sql", 1),
        ("power bi", 3),
    ]
    assert report.levels[0].evidence_id == str(bullets.ids[0])
    assert report.levels[0].must_have is True
    assert report.levels[2].must_have is False
    assert report.note
    assert len(calls) == 1, "one call covers every requirement"


def test_summary_only_and_skills_list_only_evidence_clamps_to_level_one(
    session, test_settings, monkeypatch
):
    """F5.4.1's cap, enforced in code: a list is noted, not proven — and the
    report says the row was clamped rather than hiding the adjustment."""
    payload = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 3,
                    "basis": "direct",
                    "source": "summary",
                    "evidence_id": None,
                    "transfer_reason": None,
                },
                {
                    "index": 1,
                    "level": 2,
                    "basis": "direct",
                    "source": "skills_list",
                    "evidence_id": None,
                    "transfer_reason": None,
                },
                {"index": 2, "level": 0, "basis": "none", "source": None},
            ],
            "note": "",
        }
    )
    stub(monkeypatch, [payload])

    report = grade_evidence(
        session,
        jd(),
        [],
        basis_credit=W3.basis_credit,
        summary_text="Automatizo reportes con Python y SQL.",
        skills_text="python, sql, power bi",
    )

    assert [entry.level for entry in report.levels] == [1, 1, 0]
    assert [entry.clamped for entry in report.levels] == [True, True, False]
    assert [entry.source for entry in report.levels] == ["summary", "skills_list", None]


def test_an_equivalent_is_confirmed_by_a_shared_family_or_downgraded(
    session, test_settings, monkeypatch
):
    """F5.4.1: equivalence is one hop and it is data. Tableau for Power BI is the
    PRD's own equivalent; a canonical outside the family is downgraded and the
    report records it."""
    session.add_all(
        [
            Skill(canonical="power bi", aliases=["powerbi"], lang_tags=["es"], family="bi_tool"),
            Skill(
                canonical="tableau",
                aliases=["tableau desktop"],
                lang_tags=["es"],
                family="bi_tool",
            ),
            Skill(canonical="python", aliases=["py"], lang_tags=["es"]),
        ]
    )
    session.commit()
    bullets = [
        type(
            "B",
            (),
            {
                "id": uuid.uuid4(),
                "text_es": "Mantuve tableros de Tableau",
                "text_en": None,
                "skills": ["tableau"],
            },
        )(),
        type(
            "B",
            (),
            {
                "id": uuid.uuid4(),
                "text_es": "Automaticé procesos con Python",
                "text_en": None,
                "skills": ["python"],
            },
        )(),
    ]

    def answer(cited):
        return json.dumps(
            {
                "grades": [
                    {
                        "index": 0,
                        "level": 2,
                        "basis": "equivalent",
                        "source": "bullet",
                        "evidence_id": str(cited.id),
                        "transfer_reason": "Mismo trabajo, intercambiable en semanas.",
                    }
                ],
                "note": "",
            }
        )

    stub(monkeypatch, [answer(bullets[0])])
    # Same input twice would hit the cache; these two runs must reach the stubs.
    fresh = CallOptions(bypass_cache=True)
    equivalent = grade_evidence(
        session,
        StructuredJD(must_have=["power bi"]),
        bullets,
        basis_credit=W3.basis_credit,
        options=fresh,
    ).levels[0]
    assert equivalent.basis == "equivalent", "same non-null family confirms the hop"
    assert equivalent.downgraded is False

    stub(monkeypatch, [answer(bullets[1])])
    # Only the Python bullet is supplied here: with the Tableau bullet in evidence
    # the family data has an answer for Power BI and the backstop (F5.5.2) would
    # grant it. This half is about the row the data cannot confirm at all.
    downgraded = grade_evidence(
        session,
        StructuredJD(must_have=["power bi"]),
        [bullets[1]],
        basis_credit=W3.basis_credit,
        options=fresh,
    ).levels[0]
    assert downgraded.basis == "transferable", "outside the family the credit is not granted"
    assert downgraded.downgraded is True


def test_a_transfer_basis_without_a_reason_fails_after_one_retry(
    session, test_settings, bullets, monkeypatch
):
    """F5.4.1's schema rule: a basis other than direct/none without a one-line
    transfer_reason is unusable — one retry, then it fails loudly."""
    bad = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 2,
                    "basis": "transferable",
                    "source": "bullet",
                    "evidence_id": str(bullets.ids[0]),
                    "transfer_reason": None,
                },
                {"index": 1, "level": 0, "basis": "none", "source": None},
                {"index": 2, "level": 0, "basis": "none", "source": None},
            ],
            "note": "",
        }
    )
    calls = stub(monkeypatch, [bad, bad])

    with pytest.raises(CitationViolation, match="transfer_reason"):
        grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert len(calls) == 2, "exactly one retry, then the loud failure"


def test_a_level_without_a_citation_is_retried_once_then_fails(
    session, test_settings, bullets, monkeypatch
):
    bad = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 2,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": None,
                    "transfer_reason": None,
                }
            ],
            "note": "",
        }
    )
    calls = stub(monkeypatch, [bad, bad])

    with pytest.raises(CitationViolation):
        grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert len(calls) == 2


def test_an_invented_citation_is_rejected(session, test_settings, bullets, monkeypatch):
    invented = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 2,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": str(uuid.uuid4()),
                    "transfer_reason": None,
                },
                {"index": 1, "level": 0, "basis": "none", "source": None},
                {"index": 2, "level": 0, "basis": "none", "source": None},
            ],
            "note": "",
        }
    )
    calls = stub(monkeypatch, [invented, invented])

    with pytest.raises(CitationViolation, match="never supplied"):
        grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert len(calls) == 2


def test_an_ungraded_requirement_is_not_silently_dropped(
    session, test_settings, bullets, monkeypatch
):
    partial = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 1,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": str(bullets.ids[0]),
                    "transfer_reason": None,
                }
            ],
            "note": "",
        }
    )
    stub(monkeypatch, [partial, partial])

    with pytest.raises(CitationViolation, match="no grade returned"):
        grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)


def test_a_corrected_answer_on_the_retry_is_accepted(session, test_settings, bullets, monkeypatch):
    bad = json.dumps(
        {
            "grades": [
                {
                    "index": 0,
                    "level": 2,
                    "basis": "direct",
                    "source": "bullet",
                    "evidence_id": None,
                    "transfer_reason": None,
                }
            ],
            "note": "",
        }
    )
    calls = stub(monkeypatch, [bad, grading_payload(bullets)])

    report = grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert len(report.levels) == 3
    assert len(calls) == 2


def test_a_shape_the_schema_rejects_fails_loudly(session, test_settings, bullets, monkeypatch):
    stub(monkeypatch, ["not json"])

    with pytest.raises(StructuredOutputError):
        grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)


def test_regrading_the_same_pair_reuses_the_cache(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])

    first = grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)
    second = grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert len(calls) == 1
    assert first.cached is False and second.cached is True
    assert first.levels == second.levels
    stored = session.query(LlmCall).one()
    assert stored.purpose == PURPOSE
    assert stored.prompt_version == "evidence_grade_v4"


def test_bullet_text_is_redacted_before_it_leaves(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])
    bullets.texts[0] = "Escribí a persona1@example.com sobre el reporte de Python"

    grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert "persona1@example.com" not in str(calls[0]["messages"])


def test_a_posting_without_requirements_makes_no_call(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])

    report = grade_evidence(
        session,
        StructuredJD(title="Analista"),
        list(bullets),
        basis_credit=W3.basis_credit,
    )

    assert report.levels == () and report.cached is False
    assert calls == []


def test_requirements_are_must_haves_then_nice_to_haves():
    assert requirements_of(jd()) == [("python", True), ("sql", True), ("power bi", False)]


def row(index: int, level: int, **fields) -> dict:
    """One answer row, filled the way the contract requires."""
    return {
        "index": index,
        "level": level,
        "basis": fields.get("basis", "none" if level == 0 else "direct"),
        "source": fields.get("source", None if level == 0 else "bullet"),
        "evidence_id": fields.get("evidence_id"),
        "transfer_reason": fields.get("reason"),
    }


def answer_of(*rows: dict, tasks: list[dict] | None = None) -> str:
    return json.dumps({"grades": list(rows), "task_grades": tasks or [], "note": ""})


def task_row(index: int, level: int, **fields) -> dict:
    """One task answer row, filled the way the contract requires."""
    return {
        "index": index,
        "level": level,
        "source": fields.get("source", None if level == 0 else "bullet"),
        "evidence_id": fields.get("evidence_id"),
    }


def tagged(identifier, text: str, skills: list[str]):
    """A bullet double carrying the skill chips the family check reads."""
    return type(
        "B", (), {"id": identifier, "text_es": text, "text_en": None, "skills": skills}
    )()


def test_the_family_table_reaches_the_prompt(session, test_settings, bullets, monkeypatch):
    """F5.5.2: "Only families listed here are equivalents" is only true of what
    was actually listed, so the table is rendered from the database."""
    session.add_all(
        [
            Skill(canonical="power bi", aliases=[], lang_tags=["es"], family="bi_tool"),
            Skill(canonical="tableau", aliases=[], lang_tags=["es"], family="bi_tool"),
            Skill(canonical="python", aliases=[], lang_tags=["es"]),
        ]
    )
    session.commit()
    calls = stub(monkeypatch, [grading_payload(bullets)])

    grade_evidence(
        session, jd(), list(bullets), basis_credit=W3.basis_credit
    )

    system = calls[0]["messages"][0]["content"]
    assert "bi_tool: power bi, tableau" in system
    assert "Only families listed here are equivalents" in system
    assert "python:" not in system, "a skill with no family is not listed as an equivalent"


def test_a_family_sibling_evidenced_elsewhere_stands_in_for_the_requirement(
    session, test_settings, monkeypatch
):
    """F5.5.2's candidate A: a sibling requirement this posting grades direct
    carries its level, source and citation across to the rows left at 0."""
    session.add_all(
        [
            Skill(canonical="power bi", aliases=[], lang_tags=["es"], family="bi_tool"),
            Skill(canonical="tableau", aliases=[], lang_tags=["es"], family="bi_tool"),
            Skill(canonical="looker", aliases=[], lang_tags=["es"], family="bi_tool"),
        ]
    )
    session.commit()
    cited = tagged(uuid.uuid4(), "Mantuve tableros de Power BI para 40 usuarios", ["power bi"])
    stub(
        monkeypatch,
        [
            answer_of(
                row(0, 3, evidence_id=str(cited.id)),
                row(1, 0),
                row(2, 0),
            )
        ],
    )

    report = grade_evidence(
        session,
        StructuredJD(must_have=["power bi", "tableau", "looker"]),
        [cited],
        basis_credit=W3.basis_credit,
    )

    power_bi, tableau, looker = report.levels
    assert (power_bi.level, power_bi.basis, power_bi.inferred) == (3, "direct", False)
    for entry in (tableau, looker):
        assert (entry.level, entry.basis, entry.inferred) == (3, "equivalent", True)
        assert entry.evidence_id == str(cited.id)
        assert entry.transfer_reason == "misma familia (bi_tool) que power bi"


def test_a_bullet_tagged_with_a_family_sibling_counts_level_two(
    session, test_settings, monkeypatch
):
    """F5.5.2's candidate B: no sibling requirement, but a supplied bullet is
    tagged with one — a described task, so level 2, on that bullet's id."""
    session.add_all(
        [
            Skill(canonical="google sheets", aliases=[], lang_tags=["es"], family="spreadsheet"),
            Skill(
                canonical="microsoft excel", aliases=[], lang_tags=["es"], family="spreadsheet"
            ),
        ]
    )
    session.commit()
    cited = tagged(uuid.uuid4(), "Armé el tablero mensual con Microsoft Excel", ["microsoft excel"])
    stub(monkeypatch, [answer_of(row(0, 0))])

    entry = grade_evidence(
        session,
        StructuredJD(must_have=["google sheets"]),
        [cited],
        basis_credit=W3.basis_credit,
    ).levels[0]

    assert (entry.level, entry.basis, entry.inferred) == (2, "equivalent", True)
    assert (entry.source, entry.evidence_id) == ("bullet", str(cited.id))
    assert entry.transfer_reason == "misma familia (spreadsheet) que microsoft excel"


def test_a_requirement_with_no_family_is_never_touched(
    session, test_settings, monkeypatch
):
    """The backstop reads `skills.family` and nothing else: two tools that plainly
    do the same job are not equivalents until the operator puts them in one."""
    session.add_all(
        [
            Skill(canonical="google sheets", aliases=[], lang_tags=["es"]),
            Skill(canonical="microsoft excel", aliases=[], lang_tags=["es"]),
        ]
    )
    session.commit()
    cited = tagged(uuid.uuid4(), "Armé el tablero mensual con Microsoft Excel", ["microsoft excel"])
    stub(monkeypatch, [answer_of(row(0, 0))])

    entry = grade_evidence(
        session,
        StructuredJD(must_have=["google sheets"]),
        [cited],
        basis_credit=W3.basis_credit,
    ).levels[0]

    assert (entry.level, entry.basis) == (0, "none")
    assert entry.inferred is False and entry.evidence_id is None


def test_a_direct_level_three_is_never_lowered_to_an_equivalent(
    session, test_settings, monkeypatch
):
    """The backstop only ever raises a credit: `3/3 × equivalent` never beats
    `3/3 × direct`, whatever sibling the family data offers."""
    session.add_all(
        [
            Skill(canonical="power bi", aliases=[], lang_tags=["es"], family="bi_tool"),
            Skill(canonical="tableau", aliases=[], lang_tags=["es"], family="bi_tool"),
        ]
    )
    session.commit()
    cited = tagged(uuid.uuid4(), "Mantuve tableros de Power BI", ["power bi"])
    sibling = tagged(uuid.uuid4(), "Construí tableros en Tableau", ["tableau"])
    stub(monkeypatch, [answer_of(row(0, 3, evidence_id=str(cited.id)))])

    entry = grade_evidence(
        session,
        StructuredJD(must_have=["power bi"]),
        [cited, sibling],
        basis_credit=W3.basis_credit,
    ).levels[0]

    assert (entry.level, entry.basis, entry.inferred) == (3, "direct", False)


def test_the_task_list_is_sent_and_graded_on_the_same_citation_rules(
    session, test_settings, monkeypatch
):
    """F5.5.2: responsibilities go out as a second numbered list and come back as
    `task_grades`, one row per index, on the same provenance rules."""
    cited = tagged(uuid.uuid4(), "Automaticé el reporte semanal con Python", ["python"])
    calls = stub(
        monkeypatch,
        [
            answer_of(
                row(0, 3, evidence_id=str(cited.id)),
                tasks=[task_row(0, 3, evidence_id=str(cited.id)), task_row(1, 0)],
            )
        ],
    )

    report = grade_evidence(
        session,
        StructuredJD(
            must_have=["python"],
            responsibilities=["Automaticé el reporte semanal", "Coordiné al equipo"],
        ),
        [cited],
        basis_credit=W3.basis_credit,
    )

    sent = calls[0]["messages"][1]["content"]
    assert "Tasks to grade, by index:" in sent
    assert "0\tAutomaticé el reporte semanal" in sent
    assert [(task.task, task.level, task.evidence_id) for task in report.task_levels] == [
        ("Automaticé el reporte semanal", 3, str(cited.id)),
        ("Coordiné al equipo", 0, None),
    ]


def test_a_posting_with_no_responsibilities_sends_no_task_list(
    session, test_settings, bullets, monkeypatch
):
    """An empty list would ask the model to grade zero tasks and invite an answer;
    none is sent, and a cached answer from before the field existed still loads."""
    calls = stub(monkeypatch, [grading_payload(bullets)])

    report = grade_evidence(session, jd(), list(bullets), basis_credit=W3.basis_credit)

    assert "Tasks to grade" not in calls[0]["messages"][1]["content"]
    assert report.task_levels == ()


def test_a_task_evidenced_only_in_the_skills_list_is_capped_at_one(
    session, test_settings, monkeypatch
):
    """F5.5.2: a task is proven by a described task, exactly as a requirement is —
    a line in the skills list is noted, not done."""
    stub(
        monkeypatch,
        [
            answer_of(
                row(0, 0),
                tasks=[task_row(0, 3, source="skills_list", evidence_id=None)],
            )
        ],
    )

    report = grade_evidence(
        session,
        StructuredJD(must_have=["python"], responsibilities=["Armé el reporte semanal"]),
        [],
        skills_text="reportes semanales",
        basis_credit=W3.basis_credit,
    )

    task = report.task_levels[0]
    assert (task.level, task.clamped, task.source) == (1, True, "skills_list")


class TestEvidenceCoverage:
    def levels(self, *rows: tuple[str, int, bool, str]) -> list[Level]:
        return [
            Level(requirement, level, must_have, basis)
            for requirement, level, must_have, basis in rows
        ]

    def test_full_evidence_scores_one(self):
        score = evidence_coverage(
            self.levels(("python", 3, True, "direct"), ("sql", 3, False, "direct")),
            basis_credit=W3.basis_credit,
        )

        assert score.value == pytest.approx(1.0)
        assert score.missing == []

    def test_must_haves_weigh_three_times_a_nice_to_have(self):
        """F5.5.1's formula: Σ weight(r) · credit(r) / Σ weight(r), 0.75 and 0.25."""
        score = evidence_coverage(
            self.levels(
                ("python", 3, True, "direct"),
                ("sql", 0, True, "direct"),
                ("power bi", 3, False, "direct"),
            ),
            basis_credit=W3.basis_credit,
        )

        assert score.value == pytest.approx(
            (0.75 * 1.0 + 0.25 * 1.0) / (0.75 + 0.75 + 0.25), abs=1e-4
        )
        assert score.detail["must_coverage"] == 0.5
        assert score.detail["nice_coverage"] == 1.0

    def test_the_basis_credit_multiplies_the_level(self):
        # equivalent: 3 / 3 × 0.75 = 0.75 ; transferable: 3 / 3 × 0.50 = 0.50
        score = evidence_coverage(
            self.levels(("power bi", 3, True, "equivalent")),
            basis_credit=W3.basis_credit,
        )
        transferred = evidence_coverage(
            self.levels(("mdm", 3, True, "transferable")),
            basis_credit=W3.basis_credit,
        )

        assert score.value == pytest.approx(0.75)
        assert transferred.value == pytest.approx(0.5)

    def test_the_split_sums_to_the_sub_score_and_direct_only_transfers_nothing(self):
        mixed = evidence_coverage(
            self.levels(
                ("python", 3, True, "direct"),
                ("power bi", 3, True, "equivalent"),
                ("mdm", 0, False, "none"),
            ),
            basis_credit=W3.basis_credit,
        )
        direct_only = evidence_coverage(
            self.levels(("python", 3, True, "direct")),
            basis_credit=W3.basis_credit,
        )

        assert mixed.detail["direct"] + mixed.detail["transfer"] == pytest.approx(
            mixed.value, abs=1e-4
        )
        assert mixed.detail["transfer"] > 0
        assert direct_only.detail["transfer"] == 0.0
        assert direct_only.detail["direct"] == pytest.approx(direct_only.value, abs=1e-4)

    def test_level_one_is_a_gap_not_evidence(self):
        score = evidence_coverage(
            self.levels(("python", 1, True, "direct")), basis_credit=W3.basis_credit
        )

        assert score.value == round(1 / 3, 4)
        assert score.value == pytest.approx(1 / 3, abs=1e-4)
        assert score.missing == ["python (L1)"]
        assert score.matched == []

    def test_a_single_group_is_scored_alone_and_says_so(self):
        score = evidence_coverage(
            self.levels(("python", 3, True, "direct")), basis_credit=W3.basis_credit
        )

        assert score.value == pytest.approx(1.0)
        assert score.detail["reason"] == "must_haves_only"

    def test_no_requirements_scores_zero_with_a_reason(self):
        score = evidence_coverage([], basis_credit=W3.basis_credit)

        assert score.value == 0.0
        assert score.detail["reason"] == "no_requirements"


def test_report_shape_keeps_levels_and_citations_together(
    session, test_settings, bullets, monkeypatch
):
    stub(monkeypatch, [grading_payload(bullets)])

    report: EvidenceReport = grade_evidence(
        session, jd(), list(bullets), basis_credit=W3.basis_credit
    )
    score = evidence_coverage(
        [
            Level(entry.requirement, entry.level, entry.must_have, entry.basis)
            for entry in report.levels
        ],
        basis_credit=W3.basis_credit,
    )

    # python 2, sql 1, power bi 3, all direct -> (0.75·2/3 + 0.75·1/3 + 0.25·1) / 1.75
    assert score.value == pytest.approx(1.0 / 1.75, abs=1e-4)
    assert score.missing == ["sql (L1)"]
