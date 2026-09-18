"""The model-selection harness: statistics, fixtures, and the cache-free stability path.

The provider is stubbed, so the whole experiment runs offline in CI. The load-bearing
test is `test_the_stability_path_never_reads_the_cache`: `llm_calls` doubles as a
content-hash cache, so a naive rerun would report perfect stability and measure the
cache instead of the judge.
"""

import json
import re
import zlib
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from src.analysis import analyze
from src.bullets import list_bullets
from src.extract import client
from src.extract.client import CallOptions
from src.model_selection import (
    CANDIDATES,
    PRICES,
    Candidate,
    CandidateReport,
    ModelPrice,
    PairResult,
    ProbeOutcome,
    bootstrap_ci,
    build_session,
    composition_notes,
    kendall_tau_b,
    load_pair,
    load_pairs,
    run_experiment,
    run_pair,
    spearman_rho,
    table_row,
    verify_prices,
)
from src.models import LlmCall

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


class FakeProvider:
    """Extraction and grading, derived from the payload so pairs differ.

    `vary` bumps every grading answer, which is what makes a cached answer
    distinguishable from a fresh one: a stability run that reads the cache returns
    the same levels every time.
    """

    def __init__(self, *, vary: bool = True, cost: str = "0.000100"):
        self.calls: list[dict] = []
        self.extract_calls = 0
        self.grading_calls = 0
        self.cost = cost
        self.vary = vary

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        if name == "ProbeAnswer":
            content = json.dumps({"ok": True})
        elif name == "JDProposal":
            self.extract_calls += 1
            content = PROPOSAL
        else:
            self.grading_calls += 1
            user = payload["messages"][1]["content"]
            ids = BULLET_ID.findall(user)
            variation = self.grading_calls if self.vary else 0
            base = zlib.crc32(user.encode("utf-8")) % 4
            grades = []
            for index, _requirement in enumerate(["python", "sql", "power bi"]):
                level = (base + index + variation) % 4
                citation = ids[0] if level > 0 and ids else None
                grades.append({"index": index, "level": level, "bullet_id": citation})
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
    calls_before = (provider.extract_calls, provider.grading_calls)
    rows_before = session.query(LlmCall).count()

    result = run_pair(
        CANDIDATE, pair, seed=11, repeats=3, session=session, profile_id=profile_id
    )

    assert (provider.extract_calls, provider.grading_calls) == (
        calls_before[0] + 1,
        calls_before[1] + 3,
    ), "one extraction and three gradings must reach the provider"
    assert session.query(LlmCall).count() == rows_before + 4, (
        "a bypassed call is still paid for and still written to the ledger"
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
    assert report.cost_effective() == Decimal("0.000200"), "extraction plus grading"
    assert report.cost_list() > 0
    assert report.latency_median() >= 0

    row = table_row(report)
    assert row.startswith("| fake-model |")
    assert row.count("|") == 10
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
    ]
    glm = CANDIDATES[2]
    assert glm.reasoning_effort == "low", "reasoning cannot be disabled on GLM"
    assert all(candidate.model in PRICES for candidate in CANDIDATES)


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


def test_the_price_check_is_quiet_when_nothing_moved():
    payload = {
        "data": [
            {
                "id": "deepseek/deepseek-v4.1-flash",
                "pricing": {"prompt": "0.00000015", "completion": "0.0000006"},
                "supported_parameters": ["seed", "temperature"],
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
                "supported_parameters": ["seed", "temperature"],
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
    assert "| model |" in printed and "cache bypassed" in printed
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["pairs"] == ["001-analista-riesgo-senior"]
    assert [entry["label"] for entry in payload["models"]] == [
        "deepseek-v4.1-flash",
        "gemini-3.8-flash",
        "glm-5.3 (low)",
    ]
    assert payload["models"][0]["metrics"]["stability"] is not None
