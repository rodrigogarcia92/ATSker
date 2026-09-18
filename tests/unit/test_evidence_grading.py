"""Evidence grading: citation integrity, one retry, and the coverage arithmetic.

The citation rules are the anti-fabrication guarantee at this layer: a level above
zero must name a bullet the profile actually has, and no requirement may be silently
left ungraded.
"""

import json
import uuid

import pytest

from src.extract.client import StructuredOutputError
from src.extract.grading import (
    PURPOSE,
    CitationViolation,
    EvidenceReport,
    grade_evidence,
    requirements_of,
)
from src.jd import StructuredJD
from src.models import LlmCall
from src.score.evidence import Level, evidence_coverage


def jd() -> StructuredJD:
    return StructuredJD(
        title="Data Analyst",
        must_have=["python", "sql"],
        nice_to_have=["power bi"],
    )


class Bullets:
    """Stands in for ORM bullets: grading only needs id and text."""

    def __init__(self) -> None:
        self.ids = [uuid.uuid4() for _ in range(2)]
        self.texts = [
            "Automaticé el reporte mensual con Python y reduje 30% el tiempo de cierre",
            "Mantuve tableros de Power BI para 40 usuarios",
        ]

    def __iter__(self):
        for identifier, text in zip(self.ids, self.texts, strict=True):
            yield type("B", (), {"id": identifier, "text_es": text, "text_en": None})()


@pytest.fixture
def bullets() -> Bullets:
    return Bullets()


def grading_payload(bullets: Bullets, levels=(2, 1, 3)) -> str:
    ids = [str(bullets.ids[0]), str(bullets.ids[1]), str(bullets.ids[1])]
    return json.dumps(
        {
            "grades": [
                {"index": index, "level": level, "bullet_id": (None if level == 0 else ids[index])}
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

    report = grade_evidence(session, jd(), list(bullets))

    assert [(entry.requirement, entry.level) for entry in report.levels] == [
        ("python", 2),
        ("sql", 1),
        ("power bi", 3),
    ]
    assert report.levels[0].bullet_id == str(bullets.ids[0])
    assert report.levels[0].must_have is True
    assert report.levels[2].must_have is False
    assert report.note
    assert len(calls) == 1, "one call covers every requirement"


def test_a_level_without_a_citation_is_retried_once_then_fails(
    session, test_settings, bullets, monkeypatch
):
    bad = json.dumps({"grades": [{"index": 0, "level": 2, "bullet_id": None}], "note": ""})
    calls = stub(monkeypatch, [bad, bad])

    with pytest.raises(CitationViolation):
        grade_evidence(session, jd(), list(bullets))

    assert len(calls) == 2


def test_an_invented_citation_is_rejected(session, test_settings, bullets, monkeypatch):
    invented = json.dumps(
        {
            "grades": [
                {"index": 0, "level": 2, "bullet_id": str(uuid.uuid4())},
                {"index": 1, "level": 0, "bullet_id": None},
                {"index": 2, "level": 0, "bullet_id": None},
            ],
            "note": "",
        }
    )
    calls = stub(monkeypatch, [invented, invented])

    with pytest.raises(CitationViolation, match="never supplied"):
        grade_evidence(session, jd(), list(bullets))

    assert len(calls) == 2


def test_an_ungraded_requirement_is_not_silently_dropped(
    session, test_settings, bullets, monkeypatch
):
    partial = json.dumps(
        {"grades": [{"index": 0, "level": 1, "bullet_id": str(bullets.ids[0])}], "note": ""}
    )
    stub(monkeypatch, [partial, partial])

    with pytest.raises(CitationViolation, match="no grade returned"):
        grade_evidence(session, jd(), list(bullets))


def test_a_corrected_answer_on_the_retry_is_accepted(session, test_settings, bullets, monkeypatch):
    bad = json.dumps({"grades": [{"index": 0, "level": 2, "bullet_id": None}], "note": ""})
    calls = stub(monkeypatch, [bad, grading_payload(bullets)])

    report = grade_evidence(session, jd(), list(bullets))

    assert len(report.levels) == 3
    assert len(calls) == 2


def test_a_shape_the_schema_rejects_fails_loudly(session, test_settings, bullets, monkeypatch):
    stub(monkeypatch, ["not json"])

    with pytest.raises(StructuredOutputError):
        grade_evidence(session, jd(), list(bullets))


def test_regrading_the_same_pair_reuses_the_cache(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])

    first = grade_evidence(session, jd(), list(bullets))
    second = grade_evidence(session, jd(), list(bullets))

    assert len(calls) == 1
    assert first.cached is False and second.cached is True
    assert first.levels == second.levels
    stored = session.query(LlmCall).one()
    assert stored.purpose == PURPOSE
    assert stored.prompt_version == "evidence_grade_v2"


def test_bullet_text_is_redacted_before_it_leaves(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])
    bullets.texts[0] = "Escribí a persona@example.com sobre el reporte de Python"

    grade_evidence(session, jd(), list(bullets))

    assert "persona@example.com" not in str(calls[0]["messages"])


def test_a_posting_without_requirements_makes_no_call(session, test_settings, bullets, monkeypatch):
    calls = stub(monkeypatch, [grading_payload(bullets)])

    report = grade_evidence(session, StructuredJD(title="Analista"), list(bullets))

    assert report.levels == () and report.cached is False
    assert calls == []


def test_requirements_are_must_haves_then_nice_to_haves():
    assert requirements_of(jd()) == [("python", True), ("sql", True), ("power bi", False)]


class TestEvidenceCoverage:
    def levels(self, *rows: tuple[str, int, bool]) -> list[Level]:
        return [Level(requirement, level, must_have) for requirement, level, must_have in rows]

    def test_full_evidence_scores_one(self):
        score = evidence_coverage(self.levels(("python", 3, True), ("sql", 3, False)))

        assert score.value == pytest.approx(1.0)
        assert score.missing == []

    def test_must_haves_carry_three_quarters_of_the_sub_score(self):
        # must: (3 + 0) / (3 x 2) = 0.5 ; nice: 3 / 3 = 1.0
        score = evidence_coverage(
            self.levels(("python", 3, True), ("sql", 0, True), ("power bi", 3, False))
        )

        assert score.value == pytest.approx(0.75 * 0.5 + 0.25 * 1.0)
        assert score.detail["must_coverage"] == 0.5
        assert score.detail["nice_coverage"] == 1.0

    def test_level_one_is_a_gap_not_evidence(self):
        score = evidence_coverage(self.levels(("python", 1, True)))

        assert score.value == round(1 / 3, 4)
        assert score.value == pytest.approx(1 / 3, abs=1e-4)
        assert score.missing == ["python (L1)"]
        assert score.matched == []

    def test_a_single_group_is_scored_alone_and_says_so(self):
        score = evidence_coverage(self.levels(("python", 3, True)))

        assert score.value == pytest.approx(1.0)
        assert score.detail["reason"] == "must_haves_only"

    def test_no_requirements_scores_zero_with_a_reason(self):
        score = evidence_coverage([])

        assert score.value == 0.0
        assert score.detail["reason"] == "no_requirements"


def test_report_shape_keeps_levels_and_citations_together(
    session, test_settings, bullets, monkeypatch
):
    stub(monkeypatch, [grading_payload(bullets)])

    report: EvidenceReport = grade_evidence(session, jd(), list(bullets))
    score = evidence_coverage(
        [Level(entry.requirement, entry.level, entry.must_have) for entry in report.levels]
    )

    # python 2, sql 1, power bi 3 -> must coverage (2+1)/6 = 0.5, nice 1.0
    assert score.value == pytest.approx(0.75 * 0.5 + 0.25 * 1.0)
    assert score.missing == ["sql (L1)"]
