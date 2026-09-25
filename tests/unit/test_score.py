"""Sub-scores against hand-computed values, and the aggregation arithmetic."""

from datetime import date

import pytest

from src.jd import StructuredJD
from src.score.aggregate import SUB_SCORES, SubScore, aggregate
from src.score.experience import experience_score, merge_intervals, years_held
from src.score.keywords import keyword_context
from src.score.title import seniority_of, title_alignment
from src.score.weights import W1, W2, W3, W4, Weights, WeightsV2, WeightsV3, WeightsV4

TODAY = date(2026, 1, 1)


def jd(**overrides) -> StructuredJD:
    values = {"title": "Data Analyst", "seniority": "mid", "years_required": 5.0}
    values.update(overrides)
    return StructuredJD(**values)


def test_title_overlap_is_hand_checkable():
    score = title_alignment(
        jd(title="Data Analyst", seniority="mid"),
        headline="Data Analyst",
        roles=[("Data Analyst", None, None)],
    )

    assert score.value == 1.0
    assert score.matched == ["analyst", "data"]
    assert score.missing == []
    assert score.detail["overlap"] == 1.0


def test_a_function_word_does_not_count_on_either_side():
    """F5.5.2: `de` is removed from the posting's title and the user's alike, and a
    wanted set emptied by the function words is not an overlap of zero for no reason —
    the detail says which it was."""
    score = title_alignment(
        jd(title="Analista de Datos", seniority="unknown"),
        headline=None,
        roles=[("Analista Datos", None, None)],
    )

    assert score.matched == ["analista", "datos"]
    assert score.value == pytest.approx(1.0), "'de' is not a wanted word"

    only_function_words = title_alignment(
        jd(title="de la", seniority="unknown"),
        headline=None,
        roles=[("Analista Datos", None, None)],
    )
    assert only_function_words.value == 0.0
    assert only_function_words.detail["reason"] == "only_function_words"


def test_the_most_recent_role_sets_the_rung_and_earlier_titles_never_do():
    """F5.5.2: the current role's words name the rung — `practicante` years ago must
    not decide it — and no rung anywhere means no alert, never an invented one."""
    score = title_alignment(
        jd(title="Analista de Datos", seniority="senior"),
        headline=None,
        roles=[
            ("Practicante de datos", date(2019, 1, 1), date(2019, 12, 31)),
            ("Analista de Datos", date(2020, 1, 1), None),
        ],
    )

    assert score.value == pytest.approx(1.0)
    assert score.detail["user_rung"] is None
    assert score.detail["seniority_above"] is False
    assert score.detail["seniority_below"] is False

    closed = title_alignment(
        jd(title="Analyst", seniority="mid"),
        headline=None,
        roles=[
            ("Junior Analyst", date(2018, 1, 1), date(2019, 1, 1)),
            ("Senior Analyst", date(2019, 2, 1), date(2022, 1, 1)),
        ],
    )
    assert closed.detail["user_rung"] == "senior", "the latest end date names the rung"


def test_seniority_is_an_alert_both_ways_and_never_a_subtraction():
    """F5.5.2: value is overlap; the mismatch is two booleans the report alerts on."""
    above = title_alignment(
        jd(title="Analyst", seniority="junior"),
        headline=None,
        roles=[("Senior Analyst", date(2020, 1, 1), None)],
    )
    below = title_alignment(
        jd(title="Analyst", seniority="senior"),
        headline=None,
        roles=[("Junior Analyst", date(2020, 1, 1), None)],
    )

    assert above.value == pytest.approx(1.0)
    assert above.detail["seniority_above"] is True
    assert above.detail["seniority_below"] is False
    assert below.value == pytest.approx(1.0)
    assert below.detail["seniority_below"] is True
    assert below.detail["seniority_above"] is False
    assert below.detail["user_rung"] == "junior"
    assert below.detail["jd_rung"] == "senior"


def test_the_rung_falls_back_to_the_headline_when_the_current_title_names_none():
    score = title_alignment(
        jd(title="Analyst", seniority="mid"),
        headline="Analyst senior",
        roles=[("Analista de datos", date(2020, 1, 1), None)],
    )

    assert score.detail["user_rung"] == "senior"
    assert score.detail["seniority_above"] is True
    assert score.value == pytest.approx(1.0), "the alert never touches the number"


def test_keywords_count_aliases_but_never_equivalents():
    """F5.5.1's literal screen: `PowerBI` is the same thing spelled differently and
    counts; Tableau does the same job and does not. No family lookup anywhere."""
    aliases = {"powerbi": "power bi", "power bi": "power bi", "tableau": "tableau"}
    spelled_differently = keyword_context(
        jd(raw_keywords=["power bi"]), ["Mantuve tableros de PowerBI"], aliases=aliases
    )
    equivalent_tool = keyword_context(
        jd(raw_keywords=["power bi"]), ["Mantuve tableros de Tableau"], aliases=aliases
    )

    assert spelled_differently.matched == ["power bi"]
    assert equivalent_tool.missing == ["power bi"], "an equivalent is not a keyword hit"


def test_keywords_read_the_skills_list_and_the_summary_not_only_the_bullets():
    """F5.5.1: the keyword search runs over the file — skills section included."""
    score = keyword_context(
        jd(raw_keywords=["power bi", "gobierno de datos"]),
        [
            "Reduje 30% el tiempo de reporte con Python",
            "power bi, python",
            "Cinco años de gobierno de datos.",
        ],
    )

    assert score.matched == ["power bi", "gobierno de datos"]
    assert score.value == pytest.approx(1.0)
    assert score.detail["documents"] == 3


def test_a_skill_named_only_as_a_requirement_still_counts_as_a_keyword():
    """F5.5.2: the keyword set is every term the posting asks for, so SQL named as a
    must-have is a term the document has to evidence even when no keyword list
    repeats it."""
    score = keyword_context(
        jd(must_have=["sql"], nice_to_have=["airflow"], raw_keywords=["reportes"]),
        ["Automaticé reportes con SQL"],
    )

    assert score.matched == ["sql", "reportes"]
    assert score.missing == ["airflow"]


def test_two_aliases_of_one_canonical_are_one_keyword():
    """F5.5.2: de-duplicated by the resolved key, not by the words — `powerbi` as a
    requirement and `power bi` as a keyword are one term, and the first occurrence
    is the name the report shows."""
    aliases = {"powerbi": "power bi", "power bi": "power bi"}
    score = keyword_context(
        jd(must_have=["powerbi"], raw_keywords=["power bi"]),
        ["Mantuve tableros de Power BI"],
        aliases=aliases,
    )

    assert score.matched == ["powerbi"], "one term, named by its first occurrence"
    assert score.missing == []


def test_tableau_asked_for_is_not_matched_by_power_bi_on_the_cv():
    """F5.5.2: widening what is asked for changes nothing about what answers it —
    the screen stays literal and equivalents never count."""
    aliases = {"tableau": "tableau", "power bi": "power bi"}
    score = keyword_context(
        jd(must_have=["tableau"], raw_keywords=["reportes"]),
        ["Armé reportes mensuales con Power BI"],
        aliases=aliases,
    )

    assert score.missing == ["tableau"]
    assert score.matched == ["reportes"]


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
        roles=[],
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


def full_set(skills=0.5, experience=0.5, title=1.0, keywords=0.0):
    """`w2`'s four sub-scores (PRD F5.5), in the order the report shows them."""
    return {
        "skills": sub("skills", skills),
        "experience": sub("experience", experience),
        "title": sub("title", title),
        "keywords": sub("keywords", keywords),
    }


def test_weights_sum_to_one_and_hash_the_values():
    assert W1.total() == pytest.approx(1.0), "w1 stays in the file as history"
    assert W2.total() == pytest.approx(1.0)
    assert W2.as_dict() == {
        "version": "w2",
        "skills": 0.40,
        "experience": 0.25,
        "title": 0.20,
        "keywords": 0.15,
    }, "PRD F5.5's four, and no semantic"

    renamed = Weights("w1", 0.40, 0.25, 0.20, 0.0, 0.15)
    assert renamed.config_hash() != W2.config_hash(), (
        "the field names are part of the hash: a rename is a different configuration"
    )
    same = WeightsV2("w9", 0.40, 0.25, 0.20, 0.15)
    assert same.config_hash() == W2.config_hash(), (
        "the hash covers values, not the version string"
    )


def test_w3_keeps_the_four_weights_and_hashes_the_basis_credits_with_them():
    """F5.5.1: the credits are part of the config — same weights, different credits,
    is a different configuration and the hash must say so."""
    assert W3.total() == pytest.approx(1.0)
    assert W3.version == "w3"
    assert (W3.skills, W3.experience, W3.title, W3.keywords) == (0.40, 0.25, 0.20, 0.15)
    assert W3.basis_credit == {
        "direct": 1.00,
        "equivalent": 0.75,
        "transferable": 0.50,
        "none": 0.0,
    }

    same_four = WeightsV3(
        "w3",
        skills=0.40,
        experience=0.25,
        title=0.20,
        keywords=0.15,
        basis_credit={"direct": 1.0, "equivalent": 0.5, "transferable": 0.25, "none": 0.0},
    )
    assert same_four.config_hash() != W3.config_hash()
    assert WeightsV3(
        "w3",
        skills=0.40,
        experience=0.25,
        title=0.20,
        keywords=0.15,
        basis_credit=dict(W3.basis_credit),
    ).config_hash() == W3.config_hash(), "the hash covers both halves, and only the values"


def test_w4_keeps_w3s_values_and_hashes_the_experience_split_with_them():
    """F5.5.2: `w3`'s four weights and basis credits, unchanged, plus the split that
    divides Experience — hashed with the rest, so a moved split is a new config."""
    assert W4.total() == pytest.approx(1.0)
    assert W4.version == "w4"
    assert (W4.skills, W4.experience, W4.title, W4.keywords) == (
        W3.skills,
        W3.experience,
        W3.title,
        W3.keywords,
    )
    assert dict(W4.basis_credit) == dict(W3.basis_credit)
    assert dict(W4.experience_split) == {"years": 0.6, "tasks": 0.4}

    moved = WeightsV4(
        "w4",
        skills=0.40,
        experience=0.25,
        title=0.20,
        keywords=0.15,
        basis_credit=dict(W3.basis_credit),
        experience_split={"years": 0.5, "tasks": 0.5},
    )
    assert moved.config_hash() != W4.config_hash(), "the split is hashed with the rest"


def test_aggregation_matches_the_hand_computed_weighted_sum():
    report = aggregate(full_set(), W2)

    expected = 0.40 * 0.5 + 0.25 * 0.5 + 0.20 * 1.0 + 0.15 * 0.0
    assert report.weighted == pytest.approx(expected)
    assert report.uncapped == round(100 * expected)
    assert report.capped == report.uncapped
    assert report.cap is None
    assert report.weights_version == "w2"
    assert report.unavailable == {}, "w2 declares nothing missing"
    assert report.effective_weights == {
        "skills": 0.40,
        "experience": 0.25,
        "title": 0.20,
        "keywords": 0.15,
    }, "no omission means the effective weights are the config as written"


def test_the_gate_caps_the_report_but_the_uncapped_score_survives():
    from src.parse.gate import Finding, ParseReport

    gate = ParseReport(findings=(Finding("invisible_text", "blocker", {"page": 1, "words": 12}),))

    report = aggregate(full_set(), W2, gate=gate)

    expected_weighted = 0.40 * 0.5 + 0.25 * 0.5 + 0.20 * 1.0 + 0.15 * 0.0
    assert report.weighted == pytest.approx(expected_weighted)
    assert report.uncapped == round(100 * expected_weighted)
    assert report.capped == 40
    assert report.cap == 40
    assert report.cap_reason == "invisible_text"


def test_a_report_refuses_to_aggregate_a_partial_set_of_sub_scores():
    """F5.5 keeps the guard: `w2` declares nothing missing, and that is a statement."""
    partial = full_set()
    del partial["skills"]

    with pytest.raises(ValueError, match="skills"):
        aggregate(partial, W2)


def test_report_serialises_every_sub_score_with_its_terms():
    payload = aggregate(full_set(), W2).to_dict()

    assert list(payload["sub_scores"]) == list(SUB_SCORES) == [
        "skills",
        "experience",
        "title",
        "keywords",
    ]
    assert payload["sub_scores"]["title"]["matched"] == ["title-term"]
    assert payload["weights_hash"] == W2.config_hash()


def test_without_an_omission_the_effective_weights_are_the_config():
    report = aggregate(full_set(), W2)

    assert report.unavailable == {}
    assert report.effective_weights == {name: getattr(W2, name) for name in SUB_SCORES}
    assert report.effective_weights_hash == report.weights_hash


def test_a_declared_omission_is_renormalised_and_the_shift_is_visible():
    """The guard's other half: a caller that cannot compute a component says so."""
    partial = full_set()
    del partial["keywords"]

    report = aggregate(partial, W2, unavailable={"keywords": "no_keywords_in_jd"})

    expected = (0.40 * 0.5 + 0.25 * 0.5 + 0.20 * 1.0) / 0.85
    assert report.weighted == pytest.approx(expected)
    assert report.uncapped == round(100 * expected)
    assert report.effective_weights["title"] == pytest.approx(0.20 / 0.85)
    assert sum(report.effective_weights.values()) == pytest.approx(1.0)
    assert report.unavailable == {"keywords": "no_keywords_in_jd"}

    payload = report.to_dict()
    assert payload["unavailable"] == {"keywords": "no_keywords_in_jd"}
    assert payload["effective_weights_hash"] == report.effective_weights_hash
    assert payload["effective_weights_hash"] != payload["weights_hash"], (
        "the shift from the nominal config must be visible"
    )


def test_the_effective_weights_hash_identifies_the_renormalised_configuration():
    partial = full_set()
    del partial["keywords"]
    other = full_set()
    del other["experience"]

    first = aggregate(partial, W2, unavailable={"keywords": "no_keywords_in_jd"})
    again = aggregate(partial, W2, unavailable={"keywords": "no_keywords_in_jd"})
    different = aggregate(other, W2, unavailable={"experience": "no_roles_recorded"})

    assert first.effective_weights_hash == again.effective_weights_hash
    assert first.effective_weights_hash != different.effective_weights_hash


def test_an_omission_must_be_declared_and_must_not_contradict_the_scores():
    partial = full_set()
    del partial["keywords"]

    with pytest.raises(ValueError, match="missing sub-scores"):
        aggregate(partial, W2)

    with pytest.raises(ValueError, match="declared unavailable but supplied"):
        aggregate(full_set(), W2, unavailable={"keywords": "no_keywords_in_jd"})

    with pytest.raises(ValueError, match="unknown sub-scores"):
        aggregate(partial, W2, unavailable={"keywordz": "typo"})
