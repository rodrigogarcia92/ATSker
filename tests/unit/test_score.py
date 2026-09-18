"""Sub-scores against hand-computed values, and the aggregation arithmetic."""

from datetime import date

import pytest

from src.jd import StructuredJD
from src.score.aggregate import SUB_SCORES, SubScore, aggregate
from src.score.experience import experience_score, merge_intervals, years_held
from src.score.keywords import keyword_context
from src.score.title import seniority_of, title_alignment
from src.score.weights import W1, Weights

TODAY = date(2026, 1, 1)


def jd(**overrides) -> StructuredJD:
    values = {"title": "Data Analyst", "seniority": "mid", "years_required": 5.0}
    values.update(overrides)
    return StructuredJD(**values)


def test_title_overlap_is_hand_checkable():
    score = title_alignment(
        jd(title="Data Analyst", seniority="mid"),
        headline="Data Analyst",
        role_titles=["Data Analyst"],
    )

    assert score.value == 1.0
    assert score.matched == ["analyst", "data"]
    assert score.missing == []
    assert score.detail["penalty"] == 0.0


def test_title_missing_terms_are_named():
    score = title_alignment(
        jd(title="Senior Data Analyst", seniority="senior"),
        headline="Analista de datos",
        role_titles=["Analista de datos senior"],
    )

    assert score.matched == ["analyst", "data", "senior"] or "senior" in score.matched
    assert score.detail["rung_distance"] == 0


def test_one_rung_off_costs_point_two_and_two_rungs_cost_point_five():
    one_rung = title_alignment(
        jd(title="Analyst", seniority="senior"),
        headline="Analyst mid",
        role_titles=[],
    )
    two_rungs = title_alignment(
        jd(title="Analyst", seniority="principal"),
        headline="Analyst junior",
        role_titles=[],
    )

    assert one_rung.detail["rung_distance"] == 1
    assert one_rung.value == pytest.approx(0.8)
    assert two_rungs.detail["rung_distance"] == 4
    assert two_rungs.value == pytest.approx(0.5)


def test_an_unknown_user_rung_is_not_penalised():
    """No rung in the profile means no basis for a penalty; inventing one would fabricate."""
    score = title_alignment(
        jd(title="Analyst", seniority="principal"),
        headline="Analyst",
        role_titles=["Analyst"],
    )

    assert score.detail["rung_distance"] is None
    assert score.value == pytest.approx(1.0)


def test_seniority_is_read_from_either_language():
    assert seniority_of("Senior Data Analyst") == "senior"
    assert seniority_of("Analista de datos senior") == "senior"
    assert seniority_of("Líder de datos") == "lead"
    assert seniority_of("Analista de datos") is None


def test_alias_expansion_makes_bi_and_power_bi_overlap():
    aliases = {"bi": "power bi", "power": "power bi", "powerbi": "power bi"}
    score = title_alignment(
        jd(title="BI Developer", seniority="mid"),
        headline="Power BI developer",
        role_titles=[],
        aliases=aliases,
    )

    assert "bi" in score.matched, score
    assert score.missing == ["developer"] or score.missing == []


def test_keyword_context_is_one_when_every_keyword_appears_and_zero_when_none_do():
    covers = keyword_context(jd(raw_keywords=["python", "sql"]), ["Experiencia con Python y SQL"])
    misses = keyword_context(jd(raw_keywords=["kubernetes"]), ["Experiencia con Python y SQL"])

    assert covers.value == 1.0
    assert covers.matched == ["python", "sql"]
    assert misses.value == 0.0
    assert misses.missing == ["kubernetes"]


def test_keyword_context_is_between_zero_and_one_for_a_partial_match():
    score = keyword_context(jd(raw_keywords=["python", "kubernetes"]), ["Experiencia con Python"])

    assert 0.0 < score.value < 1.0
    assert score.matched == ["python"]
    assert score.missing == ["kubernetes"]


def test_no_bullets_scores_zero_and_names_every_keyword():
    score = keyword_context(jd(raw_keywords=["python", "sql"]), [])

    assert score.value == 0.0
    assert score.missing == ["python", "sql"]


def test_experience_penalty_is_a_quarter_per_year_short():
    intervals = [(date(2022, 1, 1), date(2025, 6, 1))]  # 3.42 years

    score = experience_score(jd(years_required=5.0), intervals, today=TODAY)

    assert score.detail["deficit_years"] == pytest.approx(1.58, abs=0.02)
    assert score.value == pytest.approx(0.60, abs=0.02)
    assert score.value == pytest.approx(
        max(0.0, 1 - 0.25 * score.detail["deficit_years"]), abs=0.001
    )
    assert score.missing[0].endswith("years")


def test_meeting_the_requirement_scores_one():
    intervals = [(date(2018, 1, 1), date(2026, 1, 1))]

    score = experience_score(jd(years_required=5.0), intervals, today=TODAY)

    assert score.value == 1.0
    assert score.missing == []


def test_concurrent_roles_do_not_double_count_calendar_time():
    intervals = [
        (date(2020, 1, 1), date(2022, 1, 1)),
        (date(2021, 1, 1), date(2023, 1, 1)),
    ]

    assert years_held(intervals, today=TODAY) == pytest.approx(3.0, abs=0.02)
    assert merge_intervals(intervals) == [(date(2020, 1, 1), date(2023, 1, 1))]


def test_no_requirement_does_not_penalise():
    score = experience_score(jd(years_required=None), [], today=TODAY)

    assert score.value == 1.0
    assert score.detail["reason"] == "no_requirement"


def sub(name: str, value: float) -> SubScore:
    return SubScore(name=name, value=value, matched=[f"{name}-term"], missing=[])


def full_set(title=1.0, evidence=0.5, keyword=0.0, semantic=1.0, experience=0.5):
    return {
        "title": sub("title", title),
        "evidence": sub("evidence", evidence),
        "keyword": sub("keyword", keyword),
        "semantic": sub("semantic", semantic),
        "experience": sub("experience", experience),
    }


def test_weights_sum_to_one_and_hash_the_values():
    assert W1.total() == pytest.approx(1.0)

    changed = Weights("w2", 0.20, 0.35, 0.15, 0.10, 0.20)
    assert changed.config_hash() == W1.config_hash(), (
        "the hash covers values, not the version string"
    )

    different = Weights("w1", 0.25, 0.30, 0.15, 0.10, 0.20)
    assert different.config_hash() != W1.config_hash()


def test_aggregation_matches_the_hand_computed_weighted_sum():
    report = aggregate(full_set(), W1)

    expected = 0.20 * 1.0 + 0.35 * 0.5 + 0.15 * 0.0 + 0.10 * 1.0 + 0.20 * 0.5
    assert report.weighted == pytest.approx(expected)
    assert report.uncapped == round(100 * expected)
    assert report.capped == report.uncapped
    assert report.cap is None
    assert report.weights_version == "w1"


def test_the_gate_caps_the_report_but_the_uncapped_score_survives():
    from src.parse.gate import Finding, ParseReport

    gate = ParseReport(findings=(Finding("invisible_text", "blocker", {"page": 1, "words": 12}),))

    report = aggregate(full_set(), W1, gate=gate)

    expected_weighted = 0.20 * 1.0 + 0.35 * 0.5 + 0.15 * 0.0 + 0.10 * 1.0 + 0.20 * 0.5
    assert report.weighted == pytest.approx(expected_weighted)
    assert report.uncapped == round(100 * expected_weighted)
    assert report.capped == 40
    assert report.cap == 40
    assert report.cap_reason == "invisible_text"


def test_a_report_refuses_to_aggregate_a_partial_set_of_sub_scores():
    partial = full_set()
    del partial["evidence"]

    with pytest.raises(ValueError, match="evidence"):
        aggregate(partial, W1)


def test_report_serialises_every_sub_score_with_its_terms():
    payload = aggregate(full_set(), W1).to_dict()

    assert set(payload["sub_scores"]) == {"title", "evidence", "keyword", "semantic", "experience"}
    assert payload["sub_scores"]["title"]["matched"] == ["title-term"]
    assert payload["weights_hash"] == W1.config_hash()


def test_without_an_omission_the_effective_weights_are_the_config():
    report = aggregate(full_set(), W1)

    assert report.unavailable == {}
    assert report.effective_weights == {name: getattr(W1, name) for name in SUB_SCORES}
    assert report.effective_weights_hash == report.weights_hash


def test_renormalising_over_four_components_matches_the_hand_computed_total():
    """State doc §4 option A: the semantic weight is redistributed, not lost."""
    partial = full_set()
    del partial["semantic"]

    report = aggregate(partial, W1, unavailable={"semantic": "embeddings_not_available"})

    expected = (0.20 * 1.0 + 0.35 * 0.5 + 0.15 * 0.0 + 0.20 * 0.5) / 0.90
    assert report.weighted == pytest.approx(expected)
    assert report.uncapped == round(100 * expected)
    assert report.effective_weights["title"] == pytest.approx(0.20 / 0.90)
    assert sum(report.effective_weights.values()) == pytest.approx(1.0)
    assert report.unavailable == {"semantic": "embeddings_not_available"}

    payload = report.to_dict()
    assert payload["unavailable"] == {"semantic": "embeddings_not_available"}
    assert payload["effective_weights_hash"] == report.effective_weights_hash
    assert payload["effective_weights_hash"] != payload["weights_hash"], (
        "the shift from the nominal config must be visible"
    )


def test_the_effective_weights_hash_identifies_the_renormalised_configuration():
    partial = full_set()
    del partial["semantic"]
    other = full_set()
    del other["experience"]

    first = aggregate(partial, W1, unavailable={"semantic": "embeddings_not_available"})
    again = aggregate(partial, W1, unavailable={"semantic": "embeddings_not_available"})
    different = aggregate(other, W1, unavailable={"experience": "no_roles_recorded"})

    assert first.effective_weights_hash == again.effective_weights_hash
    assert first.effective_weights_hash != different.effective_weights_hash


def test_an_omission_must_be_declared_and_must_not_contradict_the_scores():
    partial = full_set()
    del partial["semantic"]

    with pytest.raises(ValueError, match="missing sub-scores"):
        aggregate(partial, W1)

    with pytest.raises(ValueError, match="declared unavailable but supplied"):
        aggregate(full_set(), W1, unavailable={"semantic": "embeddings_not_available"})

    with pytest.raises(ValueError, match="unknown sub-scores"):
        aggregate(partial, W1, unavailable={"semantik": "typo"})
