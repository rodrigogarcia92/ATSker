"""The model-selection harness: statistics, fixtures, and the cache-free stability path.

The provider is stubbed, so the whole experiment runs offline in CI. The load-bearing
test is `test_the_stability_path_never_reads_the_cache`: `llm_calls` doubles as a
content-hash cache, so a naive rerun would report perfect stability and measure the
cache instead of the judge.
"""

import json
import re
import zlib
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from src.analysis import analyze
from src.bullets import list_bullets
from src.extract import client
from src.extract.client import CallOptions
from src.model_selection import (
    _WEIGHTS_BY_VERSION,
    CANDIDATES,
    GLM_REFERENCE,
    PRICES,
    Candidate,
    CandidateReport,
    ModelPrice,
    PairResult,
    ProbeOutcome,
    _total_with_evidence,
    bootstrap_ci,
    build_session,
    composition_notes,
    drift_pairs,
    kendall_tau_b,
    load_pair,
    load_pairs,
    overlaps_surcharge,
    render_notes,
    render_table,
    run_experiment,
    run_pair,
    select_split,
    spearman_rho,
    surcharge_warnings,
    table_row,
    verify_prices,
)
from src.models import LlmCall
from src.score.aggregate import SubScore, aggregate
from src.score.evidence import Level, evidence_coverage
from src.score.weights import W3

SYNTHETIC = Path(__file__).resolve().parents[1] / "golden_synthetic"

PROPOSAL = json.dumps(
    {
        "language": "es",
        "title": "Analista de datos",
        "seniority": "mid",
        "years_required": 3,
        "must_have": ["python", "sql"],
        "nice_to_have": ["power bi"],
        "raw_keywords": ["reportes"],
        "hard_requirements": [],
        "location_policy": "hybrid_lima",
    }
)

BULLET_ID = re.compile(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\t")
REQUIREMENT_LINE = re.compile(r"^(\d+)\t", re.MULTILINE)


class FakeProvider:
    """Extraction and grading, derived from the payload so pairs differ.

    `vary` bumps every grading answer, which is what makes a cached answer
    distinguishable from a fresh one: a stability run that reads the cache returns
    the same levels every time. `drift` and `disqualifiers` move the extraction side
    instead, which is measured and reported separately from the judge.
    """

    def __init__(
        self,
        *,
        vary: bool = True,
        drift: bool = False,
        disqualifiers: tuple[str, ...] = (),
        cost: str = "0.000100",
    ):
        self.calls: list[dict] = []
        self.extract_calls = 0
        self.grading_calls = 0
        self.boolean_calls = 0
        self.cost = cost
        self.vary = vary
        self.drift = drift
        self.disqualifiers = disqualifiers

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        if name == "ProbeAnswer":
            content = json.dumps({"ok": True})
        elif name == "BooleanQuerySet":
            # F5.2's derivation is a third call per analysis; the harness answers it the
            # way it answers everything else, from the fixture, and counts it apart.
            self.boolean_calls += 1
            proposal = json.loads(PROPOSAL)
            content = json.dumps(
                {
                    "queries": [
                        {
                            "label": "broad",
                            "all_of": [
                                [term] for term in [proposal["title"], *proposal["must_have"]]
                            ],
                            "none_of": [],
                        }
                    ]
                }
            )
        elif name == "JDProposal":
            self.extract_calls += 1
            proposal = json.loads(PROPOSAL)
            proposal["hard_requirements"] = list(self.disqualifiers)
            if self.drift and self.extract_calls % 2 == 0:
                proposal["must_have"] = [*proposal["must_have"], "power bi"]
            content = json.dumps(proposal)
        elif name == "GapInterpretation":
            # N5's fourth call. The harness answers it from the payload like the rest:
            # one note per gap row, in the order given — the model may not add, drop
            # or reorder a gap, so a stub that did would fail the call's validation.
            user = payload["messages"][1]["content"]
            rows = user.split("came close when there is one):\n", 1)[1].split("\n\n", 1)[0]
            gaps = [
                {"requirement": parts[3], "blocking": False, "interpretation": "sintético"}
                for parts in (line.split("\t") for line in rows.splitlines())
                if len(parts) >= 4
            ]
            content = json.dumps(
                {
                    "gaps": gaps,
                    "warning": {"text": "sintético", "handling": "sintético"},
                    "not_found": "sintético",
                }
            )
        else:
            self.grading_calls += 1
            user = payload["messages"][1]["content"]
            ids = BULLET_ID.findall(user)
            indices = [int(value) for value in REQUIREMENT_LINE.findall(user)]
            variation = self.grading_calls if self.vary else 0
            base = zlib.crc32(user.encode("utf-8")) % 4
            grades = []
            for index in indices:
                level = (base + index + variation) % 4
                citation = ids[0] if level > 0 and ids else None
                grades.append(
                    {
                        "index": index,
                        "level": level,
                        "basis": "none" if level == 0 else "direct",
                        "source": None if level == 0 else "bullet",
                        "evidence_id": citation,
                        "transfer_reason": None,
                    }
                )
            content = json.dumps({"grades": grades, "note": "sintético"})
        return {
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": 2000, "completion_tokens": 120, "cost": self.cost},
            "system_fingerprint": "fp_synthetic",
        }


@pytest.fixture(autouse=True)
def fake_price(monkeypatch):
    """The stub model needs a price row; the real candidates' rows are data."""
    monkeypatch.setitem(
        PRICES,
        "fake/model-v1",
        ModelPrice(
            input_list=0.15,
            output_list=0.60,
            current_input=0.15,
            current_output=0.60,
            note="test price",
        ),
    )


@pytest.fixture
def provider(monkeypatch, test_settings) -> FakeProvider:
    stub = FakeProvider()
    monkeypatch.setattr(client, "_post", stub)
    return stub


@pytest.fixture
def pairs():
    return load_pairs(SYNTHETIC)


CANDIDATE = Candidate("fake/model-v1", "fake-model")


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def test_tau_b_is_one_for_identical_orders_and_minus_one_for_reversed():
    assert kendall_tau_b([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert kendall_tau_b([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)


def test_tau_b_corrects_for_ties_by_hand():
    """x=[1,2,3], y=[1,1,2]: 2 concordant, 1 tie on y, so 2/sqrt(2*3)."""
    expected = 2 / (6**0.5)

    assert kendall_tau_b([1, 2, 3], [1, 1, 2]) == pytest.approx(expected)


def test_tau_b_is_undefined_when_every_pair_is_a_tie():
    assert kendall_tau_b([1, 1, 1], [2, 2, 2]) is None


def test_spearman_uses_average_ranks():
    assert spearman_rho([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    # A tie in the middle becomes the average rank, so the correlation is not 1.
    tied = spearman_rho([1, 2, 3], [1, 1, 3])
    assert 0.0 < tied < 1.0


def test_the_bootstrap_interval_is_deterministic_and_brackets_the_estimate():
    xs = [10, 20, 30, 40, 50, 60]
    ys = [1, 2, 3, 4, 5, 6]

    first = bootstrap_ci(kendall_tau_b, xs, ys, resamples=200, seed=7)
    again = bootstrap_ci(kendall_tau_b, xs, ys, resamples=200, seed=7)

    assert first == again
    low, high = first
    assert low is not None and high is not None
    assert low <= kendall_tau_b(xs, ys) <= high


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def test_synthetic_pairs_load_with_their_labels(pairs):
    assert [pair.id for pair in pairs] == [
        "001-analista-riesgo-senior",
        "002-data-engineer-pipelines",
        "003-ml-platform-ingeniero",
    ]
    assert {pair.bucket for pair in pairs} == {"strong", "plausible", "stretch"}
    assert {pair.language for pair in pairs} == {"es", "en"}
    assert pairs[0].rank > pairs[2].rank
    assert pairs[0].resume.roles[0].bullets[0].text_es


def test_a_fixture_missing_a_field_names_the_field(tmp_path):
    broken = tmp_path / "broken.toml"
    broken.write_text(
        '[resume]\ndisplay_name = "X"\n[jd]\ntext = "y"\n', encoding="utf-8"
    )

    with pytest.raises(ValueError) as error:
        load_pair(broken)

    message = str(error.value)
    assert "broken.toml" in message
    assert "id" in message and "bucket" in message


def test_composition_notes_flag_a_thin_golden_set(pairs):
    notes = composition_notes(pairs)

    assert any("3 pairs" in note for note in notes)
    assert any("Spanish" in note for note in notes)
    assert any("second profile" in note for note in notes)


# --------------------------------------------------------------------------- #
# The stability path
# --------------------------------------------------------------------------- #


def test_the_stability_path_never_reads_the_cache(provider, pairs):
    """Fails if a repeat reads `llm_calls`: the levels would stop moving."""
    pair = pairs[0]
    session, profile_id = build_session(pair)
    options = CallOptions(seed=11, reasoning_effort=None)

    warmup = analyze(
        profile_id, session, jd_text=pair.jd.text, model=CANDIDATE.model, options=options
    )
    warmup_levels = tuple(int(grade["level"]) for grade in warmup.report["grades"])
    calls_before = (provider.extract_calls, provider.grading_calls, provider.boolean_calls)
    rows_before = session.query(LlmCall).count()

    result = run_pair(
        CANDIDATE, pair, seed=11, repeats=3, session=session, profile_id=profile_id
    )

    assert (provider.extract_calls, provider.grading_calls, provider.boolean_calls) == (
        calls_before[0] + 1,
        calls_before[1] + 3,
        calls_before[2] + 1,
    ), "one extraction, three gradings and the derivation must reach the provider"
    assert session.query(LlmCall).count() == rows_before + 6, (
        "a bypassed call is still paid for and still written to the ledger — extraction, "
        "grading, the boolean queries, the gap interpretation and two repeat gradings"
    )
    assert result.levels != warmup_levels, "the cached answer must not be what came back"
    assert result.stability is not None and result.stability < 1.0
    assert len(set(result.repeat_levels)) > 1


def test_repeats_that_do_not_move_report_perfect_stability(monkeypatch, test_settings, pairs):
    stub = FakeProvider(vary=False)
    monkeypatch.setattr(client, "_post", stub)
    session, profile_id = build_session(pairs[0])

    result = run_pair(
        CANDIDATE, pairs[0], seed=11, repeats=3, session=session, profile_id=profile_id
    )

    assert result.stability == pytest.approx(1.0)
    assert result.max_score_delta == 0
    assert result.changed_ordinals == 0.0


def test_moving_ordinals_show_up_in_the_score_delta(provider, pairs):
    session, profile_id = build_session(pairs[0])

    result = run_pair(
        CANDIDATE, pairs[0], seed=11, repeats=3, session=session, profile_id=profile_id
    )

    assert result.changed_ordinals > 0
    assert result.max_score_delta >= 1
    assert len(result.repeat_totals) == 3


def _first_levels(analysis) -> list[Level]:
    return [
        Level(grade["requirement"], grade["level"], grade["must_have"], grade["basis"])
        for grade in analysis.report["grades"]
    ]


def _analysis(provider, pairs):
    pair = pairs[0]
    session, profile_id = build_session(pair)
    return analyze(
        profile_id,
        session,
        jd_text=pair.jd.text,
        model=CANDIDATE.model,
        options=CallOptions(seed=11, reasoning_effort=None),
    )


def test_a_repeat_equal_to_the_first_grading_reproduces_the_w4_total(provider, pairs):
    analysis = _analysis(provider, pairs)

    assert analysis.report["score"]["weights_version"] == "w4"
    assert _total_with_evidence(analysis, _first_levels(analysis)) == (
        analysis.report["score"]["uncapped"]
    )


def test_a_repeat_equal_to_the_first_grading_reproduces_a_w3_total(provider, pairs):
    analysis = _analysis(provider, pairs)
    report = json.loads(json.dumps(analysis.report))
    report["score"]["weights_version"] = "w3"
    report["score"]["uncapped"] = aggregate(
        {
            **{
                name: SubScore(name=name, value=float(entry["value"]))
                for name, entry in report["score"]["sub_scores"].items()
                if name != "skills"
            },
            "skills": evidence_coverage(_first_levels(analysis), basis_credit=W3.basis_credit),
        },
        W3,
    ).uncapped

    assert _total_with_evidence(SimpleNamespace(report=report), _first_levels(analysis)) == (
        report["score"]["uncapped"]
    )


def test_the_total_is_rebuilt_under_the_weight_set_the_report_names(
    provider, pairs, monkeypatch
):
    """w3 and w4 carry the same numbers today, so make them differ to prove the lookup."""
    analysis = _analysis(provider, pairs)
    halved = replace(W3, basis_credit={"direct": 0.5, "equivalent": 0.4, "transferable": 0.3})
    monkeypatch.setitem(_WEIGHTS_BY_VERSION, "w3", halved)
    report = json.loads(json.dumps(analysis.report))
    report["score"]["weights_version"] = "w3"
    levels = _first_levels(analysis)

    as_w3 = _total_with_evidence(SimpleNamespace(report=report), levels)
    as_w4 = _total_with_evidence(analysis, levels)

    assert as_w4 == analysis.report["score"]["uncapped"]
    assert as_w3 < as_w4, "w3's smaller basis credits lower the Skills sub-score"


def test_an_unknown_weights_version_raises(provider, pairs):
    analysis = _analysis(provider, pairs)
    report = json.loads(json.dumps(analysis.report))
    report["score"]["weights_version"] = "w9"

    with pytest.raises(ValueError, match="w9"):
        _total_with_evidence(SimpleNamespace(report=report), _first_levels(analysis))


# --------------------------------------------------------------------------- #
# Extraction drift, which the judge's number must not absorb
# --------------------------------------------------------------------------- #


def test_the_drift_sample_is_the_first_and_last_pair(pairs):
    assert [pair.id for pair in drift_pairs(pairs)] == [
        "001-analista-riesgo-senior",
        "003-ml-platform-ingeniero",
    ]
    assert [pair.id for pair in drift_pairs(pairs[:1])] == ["001-analista-riesgo-senior"]


def test_extraction_drift_moves_while_the_judge_stands_still(monkeypatch, test_settings, pairs):
    """The two numbers answer different questions, so they are reported apart."""
    stub = FakeProvider(vary=False, drift=True)
    monkeypatch.setattr(client, "_post", stub)

    report = run_experiment(pairs, [CANDIDATE], seed=11, repeats=3)[0]

    assert report.stability() == pytest.approx(1.0), "the judge's own answer never moved"
    assert report.drift is not None
    assert report.drift.repeats == 3
    assert report.drift.count_range == 1, "every second reading added a requirement"
    assert report.drift.mean_jaccard < 1.0
    assert report.drift.identical_share == 0.0
    assert report.drift.pair_ids == ("001-analista-riesgo-senior", "003-ml-platform-ingeniero")
    assert stub.extract_calls == len(pairs) + 3 * 2, "every pair, then three readings of two"
    assert "extraction drift, separate from the judge" in render_notes([report])


def test_a_degree_ask_is_reported_and_never_graded(monkeypatch, test_settings, pairs):
    """PRD F4.4 keeps disqualifiers out of the number, and the grader sees bullets only."""
    stub = FakeProvider(vary=False, disqualifiers=("titulo universitario",))
    monkeypatch.setattr(client, "_post", stub)

    report = run_experiment(pairs, [CANDIDATE], seed=11, repeats=1)[0]

    assert report.disqualifiers() == ["titulo universitario"] * len(pairs)
    assert "titulo universitario" not in report.pairs[0].requirements
    notes = render_notes([report])
    assert "reported, never graded (PRD F4.4)" in notes
    assert f"{len(pairs)} in {len(pairs)} pairs" in notes
    assert notes.count("'titulo universitario'") == 1, "one example, not one per pair"


# --------------------------------------------------------------------------- #
# The run window
# --------------------------------------------------------------------------- #


def test_the_recorded_surcharge_windows_match_the_published_ones():
    """DeepSeek doubles on weekdays 01:00-04:00 and 06:00-10:00 UTC; weekends do not."""
    windows = PRICES["deepseek/deepseek-v4.1-flash"].surcharges
    monday_peak = datetime(2026, 9, 21, 2, 30, tzinfo=UTC)
    tuesday_morning = datetime(2026, 9, 22, 6, 30, tzinfo=UTC)
    monday_midday = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)
    saturday_peak = datetime(2026, 9, 19, 2, 30, tzinfo=UTC)

    assert overlaps_surcharge(windows, monday_peak, monday_peak)
    assert overlaps_surcharge(windows, tuesday_morning, tuesday_morning)
    assert not overlaps_surcharge(windows, monday_midday, monday_midday)
    assert not overlaps_surcharge(windows, saturday_peak, saturday_peak)


def test_a_run_starting_inside_a_window_is_announced():
    monday_peak = datetime(2026, 9, 21, 2, 30, tzinfo=UTC)
    monday_midday = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)

    notes = surcharge_warnings(CANDIDATES, now=monday_peak)

    assert any("this run starts inside" in note for note in notes)
    assert surcharge_warnings(CANDIDATES, now=monday_midday) == []


def test_every_candidate_and_pair_records_when_it_ran(provider, pairs):
    reports = run_experiment(pairs, [CANDIDATE], seed=11, repeats=1)
    report = reports[0]

    assert report.started_at is not None and report.finished_at is not None
    assert report.pairs[0].started_at <= report.pairs[-1].finished_at
    assert report.finished_at >= report.pairs[-1].finished_at
    assert report.pairs[0].in_surcharge_window is False, "the fake price row has no overrides"

    table = render_table(reports, pairs=len(pairs))
    assert "Run window" in table and "candidates started" in table
    assert "all 1 inside the" in table
    assert "time-of-day price overrides: none recorded" in render_notes(reports)


def test_the_table_and_the_notes_carry_the_reasoning_setting(provider, pairs):
    pinned = Candidate("fake/model-v1", "fake-model", reasoning_effort="low")

    report = run_experiment(pairs, [pinned], seed=11, repeats=1)[0]

    assert "| fake-model | low |" in table_row(report)
    assert "- reasoning effort: low" in render_notes([report])


# --------------------------------------------------------------------------- #
# The experiment
# --------------------------------------------------------------------------- #


def test_the_experiment_reports_every_column_of_the_table(provider, pairs):
    reports = run_experiment(pairs, [CANDIDATE], seed=11, repeats=3)

    assert len(reports) == 1
    report = reports[0]
    assert report.tau_b() is not None
    assert report.rho() is not None
    assert report.stability() is not None
    assert report.cost_effective() == Decimal("0.000400"), (
        "extraction, grading, the boolean queries and the gap interpretation"
    )
    assert report.cost_list() > 0
    assert report.latency_median() >= 0

    row = table_row(report)
    assert row.startswith("| fake-model | provider default |")
    assert row.count("|") == 11
    assert "pass" in row or "below gate" in row


def test_the_budget_is_judged_at_list_prices_not_the_promotional_rate(provider, pairs, monkeypatch):
    monkeypatch.setitem(
        PRICES,
        "fake/model-v1",
        ModelPrice(
            input_list=20.0,
            output_list=20.0,
            current_input=0.01,
            current_output=0.01,
            note="test",
        ),
    )

    reports = run_experiment(pairs, [CANDIDATE], seed=11, repeats=1)

    assert "over budget at list" in reports[0].verdict()


def test_a_candidate_that_cannot_be_reached_is_reported_not_crashed(
    monkeypatch, test_settings, pairs
):
    def unreachable(payload, api_key):
        raise RuntimeError("no route to provider")

    monkeypatch.setattr(client, "_post", unreachable)

    report = run_experiment(pairs, [CANDIDATE], seed=11, repeats=1)[0]

    assert report.probe.ok is False
    assert report.pairs == ()
    assert report.verdict() == "unavailable"
    assert "no route to provider" in report.probe.error


def test_the_json_detail_carries_the_per_pair_evidence(provider, pairs):
    from src.model_selection import report_to_json

    payload = report_to_json(run_experiment(pairs, [CANDIDATE], seed=11, repeats=3)[0])

    assert json.dumps(payload), "must be JSON-serialisable"
    assert payload["metrics"]["tau_b"] is not None
    assert payload["metrics"]["cost_effective_min"] is not None
    assert len(payload["pairs"]) == 3
    assert payload["pairs"][0]["repeat_levels"], "the repeats travel with the result"
    assert payload["pairs"][0]["requirements"] == ["python", "sql", "power bi"]
    assert payload["pairs"][0]["in_surcharge_window"] is False
    assert payload["pairs"][0]["started_at"].endswith("Z"), "the window is recorded in UTC"
    assert payload["started_at"] is not None and payload["finished_at"] is not None
    assert payload["drift"]["pair_ids"] == [
        "001-analista-riesgo-senior",
        "003-ml-platform-ingeniero",
    ]
    assert payload["metrics"]["disqualifiers"] == []
    assert payload["metrics"]["surcharge_pairs"] == 0


# --------------------------------------------------------------------------- #
# Aggregates that only make sense with data
# --------------------------------------------------------------------------- #


def pair_result(**overrides) -> PairResult:
    values = {
        "pair_id": "x",
        "language": "es",
        "bucket": "strong",
        "rank": 2,
        "requirements": ("python",),
        "total": 50,
        "levels": (2,),
        "repeat_totals": (50, 50, 50),
        "repeat_levels": ((2,), (2,), (2,)),
        "cost_usd": Decimal("0.001"),
        "stability_cost_usd": Decimal("0.002"),
        "prompt_tokens": 2000,
        "completion_tokens": 100,
        "latency_s": 2.0,
        "fingerprint": None,
    }
    values.update(overrides)
    return PairResult(**values)


def report_with(*pairs: PairResult, reference: bool = False) -> CandidateReport:
    return CandidateReport(
        candidate=Candidate("fake/model-v1", "fake-model", reference=reference),
        probe=ProbeOutcome(
            model="fake/model-v1", ok=True, seed_accepted=True, fingerprint="fp"
        ),
        pairs=pairs,
        seed=11,
        repeats=3,
    )


def test_the_verdict_gates_on_rho_and_flags_instability():
    stable_but_wrong = report_with(
        pair_result(
            pair_id="a",
            rank=2,
            total=10,
            repeat_totals=(10, 10, 10),
            repeat_levels=((1, 0), (1, 0), (1, 0)),
        ),
        pair_result(
            pair_id="b",
            rank=0,
            total=90,
            repeat_totals=(90, 90, 90),
            repeat_levels=((3, 3), (3, 3), (3, 3)),
        ),
    )

    assert "below gate" in stable_but_wrong.verdict()

    unstable = report_with(
        pair_result(
            pair_id="a",
            rank=2,
            total=50,
            repeat_totals=(40, 50, 60),
            repeat_levels=((0, 1), (2, 1), (3, 0)),
        )
    )
    assert "unstable" in unstable.verdict()


def test_a_reference_run_is_never_a_verdict():
    report = report_with(pair_result(), reference=True)
    assert report.verdict() == "reference only"


def test_the_seed_note_says_what_the_provider_did():
    accepted = ProbeOutcome(model="m", ok=True, seed_accepted=True, fingerprint="fp")
    refused = ProbeOutcome(model="m", ok=True, seed_accepted=False, fingerprint=None)
    dead = ProbeOutcome(model="m", ok=False, seed_accepted=None, fingerprint=None, error="boom")

    assert "seed accepted" in accepted.seed_note
    assert "fingerprint" in accepted.seed_note
    assert "rejected" in refused.seed_note
    assert dead.seed_note == "unavailable"


def test_the_candidate_list_matches_the_decided_set():
    assert [candidate.model for candidate in CANDIDATES] == [
        "deepseek/deepseek-v4.1-flash",
        "google/gemini-3.8-flash",
        "z-ai/glm-5.3",
        "openai/gpt-6.1-sol",
        "anthropic/claude-haiku-5.5",
    ]
    assert [candidate.reasoning_effort for candidate in CANDIDATES] == ["low"] * 4 + ["high"], (
        "every candidate is pinned to the lowest effort its provider advertises: the run "
        "compares models, not effort levels; Haiku 5.5 is the operator's trial at high"
    )
    assert [candidate.model for candidate in CANDIDATES if candidate.baseline] == [
        "google/gemini-3.8-flash"
    ], "exactly one baseline: the production model"
    assert GLM_REFERENCE.reference and GLM_REFERENCE.reasoning_effort == "max"
    assert all(candidate.model in PRICES for candidate in CANDIDATES)


def test_haiku_5_5_is_a_candidate_but_not_the_baseline_and_runs_at_high():
    from scripts.model_selection import candidate_selection

    haiku = next(item for item in CANDIDATES if item.model == "anthropic/claude-haiku-5.5")

    assert haiku.label == "haiku-5.5" and not haiku.baseline and not haiku.reference
    assert haiku.reasoning_effort == "high"
    assert PRICES[haiku.model].input_list == PRICES[haiku.model].current_input == 0.10
    assert PRICES[haiku.model].output_list == PRICES[haiku.model].current_output == 0.50
    assert [item.label for item in candidate_selection("haiku-5.5")] == ["haiku-5.5"]
    assert [item.model for item in candidate_selection("gemini-3.8-flash,haiku-5.5")] == [
        "google/gemini-3.8-flash",
        "anthropic/claude-haiku-5.5",
    ]


def test_building_the_same_pair_twice_produces_the_same_ids(pairs):
    """Stable citation targets are what let two reports of the same pair be compared."""
    first_session, first_profile = build_session(pairs[0])
    second_session, second_profile = build_session(pairs[0])

    assert [bullet.id for bullet in list_bullets(first_profile, first_session)] == [
        bullet.id for bullet in list_bullets(second_profile, second_session)
    ]


# --------------------------------------------------------------------------- #
# Prices and the CLI
# --------------------------------------------------------------------------- #


ADVERTISED = ["seed", "temperature", "reasoning", "structured_outputs", "response_format"]


def test_the_price_check_is_quiet_when_nothing_moved():
    payload = {
        "data": [
            {
                "id": "deepseek/deepseek-v4.1-flash",
                "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                "supported_parameters": ADVERTISED,
            }
        ]
    }

    assert verify_prices([CANDIDATES[0]], fetch=lambda: payload) == []


def test_the_price_check_flags_a_promotion_that_ended():
    """The discounted output rate going back to list is the case that matters."""
    payload = {
        "data": [
            {
                "id": "google/gemini-3.8-flash",
                "pricing": {"prompt": "0.00000075", "completion": "0.0000075"},
                "supported_parameters": ADVERTISED,
            }
        ]
    }

    notes = verify_prices([CANDIDATES[1]], fetch=lambda: payload)

    assert any("price list changed" in note for note in notes)


def test_the_price_check_flags_a_provider_that_stopped_advertising_seed():
    payload = {
        "data": [
            {
                "id": "z-ai/glm-5.3",
                "pricing": {"prompt": "0.0000014", "completion": "0.0000044"},
                "supported_parameters": ["temperature"],
            }
        ]
    }

    notes = verify_prices([CANDIDATES[2]], fetch=lambda: payload)

    assert any("no longer advertises seed" in note for note in notes)


def test_the_price_check_survives_no_network():
    def offline():
        raise httpx.ConnectError("offline")

    notes = verify_prices(CANDIDATES, fetch=offline)

    assert len(notes) == 1
    assert "price check skipped" in notes[0]


def sol_entry(**overrides) -> dict:
    entry = {
        "id": "openai/gpt-6.1-sol",
        "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        "supported_parameters": ADVERTISED,
        "supported_efforts": ["low", "medium", "high"],
    }
    entry.update(overrides)
    return entry


SOL = next(candidate for candidate in CANDIDATES if candidate.label == "gpt-6.1-sol")
GEMINI = next(candidate for candidate in CANDIDATES if candidate.baseline)


def test_the_price_check_is_quiet_for_sol_when_everything_is_advertised():
    assert verify_prices([SOL], fetch=lambda: {"data": [sol_entry()]}) == []


def test_the_price_check_warns_when_structured_outputs_is_missing():
    advertised = [name for name in ADVERTISED if name != "structured_outputs"]

    notes = verify_prices(
        [SOL], fetch=lambda: {"data": [sol_entry(supported_parameters=advertised)]}
    )

    assert len(notes) == 1
    assert "openai/gpt-6.1-sol" in notes[0] and "structured_outputs" in notes[0]


def test_the_price_check_warns_when_temperature_is_missing():
    advertised = [name for name in ADVERTISED if name != "temperature"]

    notes = verify_prices(
        [SOL], fetch=lambda: {"data": [sol_entry(supported_parameters=advertised)]}
    )

    assert any("no longer advertises temperature" in note for note in notes)
    assert '"openai/gpt-6.1-sol": ["temperature"]' in notes[0], "the exact entry to add"
    assert "src/extract/model_params.json" in notes[0]


def test_the_price_check_warns_when_the_effort_is_not_advertised():
    notes = verify_prices(
        [SOL], fetch=lambda: {"data": [sol_entry(supported_efforts=["medium", "high"])]}
    )

    assert len(notes) == 1
    assert "'low'" in notes[0] and "medium, high" in notes[0]


def test_the_effort_check_is_silent_when_the_api_advertises_no_list():
    entry = sol_entry()
    del entry["supported_efforts"]

    assert verify_prices([SOL], fetch=lambda: {"data": [entry]}) == []


def test_the_cli_runs_offline_against_the_synthetic_pairs(
    provider, monkeypatch, tmp_path, capsys
):
    """The same code path the operator runs, minus the provider and the network."""
    import src.model_selection as module
    from scripts import model_selection as cli

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(module, "_fetch_models", offline)
    out = tmp_path / "detail.json"

    code = cli.main(
        ["--pairs", str(SYNTHETIC), "--out", str(out), "--limit", "1", "--repeats", "2"]
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert "price check skipped" in printed
    assert "| model | reasoning |" in printed and "cache bypassed" in printed
    assert "extraction drift measured separately" in printed
    assert "| glm-5.3 | low |" in printed
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["pairs"] == ["001-analista-riesgo-senior"]
    assert [entry["label"] for entry in payload["models"]] == [
        "gemini-3.8-flash",
        "deepseek-v4.1-flash",
        "glm-5.3",
        "gpt-6.1-sol",
        "haiku-5.5",
    ], "the baseline runs first"
    assert [entry["reasoning_effort"] for entry in payload["models"]] == ["low"] * 4 + ["high"]
    assert [entry["baseline"] for entry in payload["models"]] == [True, False, False, False, False]
    assert payload["models"][0]["metrics"]["stability"] is not None
    assert payload["models"][0]["drift"] is not None
    assert payload["models"][0]["drift"]["repeats"] == 2


# --------------------------------------------------------------------------- #
# The dev split only, by default (PRD F5.5.2, §9)
# --------------------------------------------------------------------------- #


def _offline(monkeypatch):
    import src.model_selection as module

    def offline():
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(module, "_fetch_models", offline)


def test_the_synthetic_pairs_carry_their_split(pairs):
    assert [pair.split for pair in pairs] == ["dev", "dev", "test"]


def test_select_split_keeps_only_the_requested_split(pairs):
    assert [pair.split for pair in select_split(pairs, "dev")] == ["dev", "dev"]
    assert [pair.split for pair in select_split(pairs, "test")] == ["test"]
    assert len(select_split(pairs, "all")) == 3


def test_a_split_that_selects_nothing_is_a_clear_error_never_a_fallback(pairs):
    unlabelled = [pair.model_copy(update={"split": None}) for pair in pairs]

    with pytest.raises(ValueError) as error:
        select_split(unlabelled, "dev")

    message = str(error.value)
    assert "'dev' split selects no pair" in message
    assert "3 loaded, 0 carry a `split` key" in message
    assert 'split = "dev"' in message


def test_the_composition_notes_say_the_split_and_its_count(pairs):
    notes = composition_notes(select_split(pairs, "dev"), split="dev")

    assert notes[0] == "split dev: 2 pairs"


def test_the_default_run_loads_the_dev_pairs_only(provider, monkeypatch, tmp_path, capsys):
    from scripts import model_selection as cli

    _offline(monkeypatch)
    out = tmp_path / "detail.json"

    code = cli.main(
        ["--pairs", str(SYNTHETIC), "--out", str(out), "--models", "gemini-3.8-flash",
         "--repeats", "2"]
    )

    printed = capsys.readouterr().out
    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["pairs"] == [
        "001-analista-riesgo-senior",
        "002-data-engineer-pipelines",
    ]
    assert "2 pairs ·" in printed and "split dev: 2 pairs" in printed
    assert "meant to be scored once" not in printed


@pytest.mark.parametrize("split", ["test", "all"])
def test_the_test_split_needs_unseal(provider, tmp_path, split, capsys):
    from scripts import model_selection as cli

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--pairs", str(SYNTHETIC), "--out", str(tmp_path / "x.json"), "--split", split])

    assert exit_info.value.code == 2
    assert "--unseal" in capsys.readouterr().err
    assert not (tmp_path / "x.json").exists()


def test_unsealing_the_test_split_warns_that_it_is_scored_once(
    provider, monkeypatch, tmp_path, capsys
):
    from scripts import model_selection as cli

    _offline(monkeypatch)
    out = tmp_path / "detail.json"

    code = cli.main(
        ["--pairs", str(SYNTHETIC), "--out", str(out), "--models", "gemini-3.8-flash",
         "--repeats", "2", "--split", "test", "--unseal"]
    )

    assert code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["pairs"] == ["003-ml-platform-ingeniero"]
    assert "meant to be scored once" in capsys.readouterr().out


def test_pairs_with_no_split_stop_the_run_with_the_clear_message(
    provider, tmp_path, capsys
):
    from scripts import model_selection as cli

    pairs_dir = tmp_path / "pairs"
    pairs_dir.mkdir()
    for path in SYNTHETIC.glob("*.toml"):
        text = re.sub(r'^split = .*\n', "", path.read_text(encoding="utf-8"), flags=re.M)
        (pairs_dir / path.name).write_text(text, encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--pairs", str(pairs_dir), "--out", str(tmp_path / "x.json")])

    assert exit_info.value.code == 2
    assert "selects no pair" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# GPT-6.1 Sol against the production model (PRD §7, §11)
# --------------------------------------------------------------------------- #


def test_the_models_flag_selects_exactly_the_named_models_with_the_baseline_first():
    from scripts.model_selection import candidate_selection

    for spelling in ("gemini-3.8-flash,gpt-6.1-sol", "gpt-6.1-sol, gemini-3.8-flash"):
        chosen = candidate_selection(spelling)

        assert [candidate.model for candidate in chosen] == [
            "google/gemini-3.8-flash",
            "openai/gpt-6.1-sol",
        ]
    assert candidate_selection("")[0].baseline, "the default run puts the baseline first too"


def labelled_report(
    candidate: Candidate,
    *,
    total: int,
    cost: tuple[int, int],
    latency: float,
    repeat_totals: tuple[int, ...] = (50, 50, 50),
) -> CandidateReport:
    """Two pairs ordered like their buckets, so tau-b and rho are 1 for every model."""
    prompt_tokens, completion_tokens = cost
    return CandidateReport(
        candidate=candidate,
        probe=ProbeOutcome(model=candidate.model, ok=True, seed_accepted=True, fingerprint="fp"),
        pairs=(
            pair_result(
                pair_id="a",
                rank=2,
                total=total,
                repeat_totals=repeat_totals,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_s=latency,
            ),
            pair_result(
                pair_id="b",
                rank=0,
                total=10,
                repeat_totals=(10, 10, 10),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_s=latency,
            ),
        ),
        seed=11,
        repeats=3,
    )


def test_the_table_prints_the_baseline_first_and_the_deltas_against_it():
    baseline = labelled_report(GEMINI, total=90, cost=(1000, 100), latency=2.0)
    sol = labelled_report(
        SOL, total=60, cost=(1000, 500), latency=5.5, repeat_totals=(40, 50, 60)
    )

    table = render_table([sol, baseline], pairs=2)

    main = [line.split(" | ")[0] for line in table.splitlines() if line.startswith("| ")]
    assert main[1:3] == ["| gemini-3.8-flash", "| gpt-6.1-sol"], "the baseline row comes first"
    assert "Δ vs baseline (gemini-3.8-flash)" in table
    delta_line = table.splitlines()[-1]
    cells = [cell.strip() for cell in delta_line.strip("|").split("|")]
    assert cells[0] == "gpt-6.1-sol"
    # Both models order the two pairs like their buckets, so tau-b and rho do not move.
    assert cells[1:3] == ["+0.00", "+0.00"]
    assert cells[3] == "+20", "max score delta: 20 for sol against 0 for the baseline"
    # Sol: $0.002 + $0.005 = $0.007. Gemini: $0.00075 + $0.00075 = $0.0015.
    assert cells[4] == "+$0.005500"
    assert cells[5] == "+3.5s"


def test_no_baseline_in_the_run_says_so_instead_of_inventing_deltas():
    sol = labelled_report(SOL, total=60, cost=(1000, 500), latency=5.5)

    table = render_table([sol], pairs=2)

    assert "No baseline model in this run" in table
    assert "Δ tau-b" not in table


def test_cost_per_analysis_at_list_prices_for_sol():
    """(1,000 in, 500 out) at $2/$10 per M: $0.002 + $0.005."""
    report = labelled_report(SOL, total=60, cost=(1000, 500), latency=1.0)

    assert report.cost_list() == Decimal("0.007")
    assert not report.cost_over_cap()
    assert "$0.007000 |" in table_row(report) and "OVER" not in table_row(report)


def test_the_single_track_cost_is_flagged_over_the_prd_cap():
    over = labelled_report(SOL, total=60, cost=(1000, 1900), latency=1.0)  # $0.021
    at_cap = labelled_report(SOL, total=60, cost=(1000, 1800), latency=1.0)  # $0.020

    assert over.cost_list() == Decimal("0.021")
    assert over.cost_over_cap() and "$0.021000 OVER" in table_row(over)
    assert not at_cap.cost_over_cap() and "OVER" not in table_row(at_cap)
    assert "over budget at list" in over.verdict()


def test_the_cost_column_counts_the_first_analysis_only_not_the_repeats(provider, pairs):
    """The repeats' grading calls are priced as stability cost, never as the analysis."""
    report = run_experiment(pairs[:1], [SOL], seed=11, repeats=3)[0]

    (pair,) = report.pairs
    assert pair.stability_cost_usd > 0
    assert pair.prompt_tokens == 4 * 2000, "extraction, grading, boolean queries, gap notes"
    assert report.cost_list() == (
        Decimal("2.0") * pair.prompt_tokens / 1_000_000
        + Decimal("10.0") * pair.completion_tokens / 1_000_000
    )


def test_the_json_detail_marks_the_baseline_and_the_cap():
    from src.model_selection import report_to_json

    payload = report_to_json(labelled_report(GEMINI, total=90, cost=(1000, 100), latency=2.0))

    assert payload["baseline"] is True
    assert payload["metrics"]["cost_list_over_cap"] is False
    assert payload["model"] == "google/gemini-3.8-flash"


def test_sol_has_a_dated_list_price():
    from src.model_selection import PRICES_READ_ON

    price = PRICES["openai/gpt-6.1-sol"]

    assert (price.input_list, price.output_list) == (2.0, 10.0)
    assert (price.current_input, price.current_output) == (2.0, 10.0)
    assert "2026-09-30" in price.note and "reasoning tokens bill as output" in price.note
    assert PRICES_READ_ON == "2026-09-30"
