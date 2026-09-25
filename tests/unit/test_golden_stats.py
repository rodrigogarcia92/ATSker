"""Agreement statistics for the golden-set runs (queue A.4, resume §5).

Hand-computed values below are worked out in the test docstrings from the
definitions in `golden_stats`'s module docstring — ties included, because the
rater's scores tie and the tie correction is the whole point of tau-b.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts import golden_run, golden_stats
from src.score.aggregate import SubScore, aggregate
from src.score.weights import W2, W3
from tests import golden_support as support

SUB_SCORE_NAMES = ("skills", "experience", "title", "keywords")


def test_tau_b_and_rho_match_hand_computed_values_with_ties():
    """Worked cases:

    x=[1,1,2], y=[1,2,2] — pairs: one x-tie, one y-tie, one concordant.
    tau-b = 1 / sqrt((1+0+1)(1+0+1)) = 0.5. Average ranks x=[1.5,1.5,3],
    y=[1,2.5,2.5]: rho = 0.75 / 1.5 = 0.5.

    x=[1,1,2], y=[2,2,1] — the pair tied in both drops out; two discordant.
    tau-b = -2/2 = -1; ranks give rho = -1.

    x=[1,2,3], y=[3,1,2] — one concordant, two discordant, no ties:
    tau-b = -1/3; rho = -0.5.
    """
    assert golden_stats.kendall_tau_b([1, 1, 2], [1, 2, 2]) == pytest.approx(0.5)
    assert golden_stats.spearman([1, 1, 2], [1, 2, 2]) == pytest.approx(0.5)
    assert golden_stats.kendall_tau_b([1, 1, 2], [2, 2, 1]) == pytest.approx(-1.0)
    assert golden_stats.spearman([1, 1, 2], [2, 2, 1]) == pytest.approx(-1.0)
    assert golden_stats.kendall_tau_b([1, 2, 3], [3, 1, 2]) == pytest.approx(-1 / 3)
    assert golden_stats.spearman([1, 2, 3], [3, 1, 2]) == pytest.approx(-0.5)
    assert golden_stats.kendall_tau_b([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert golden_stats.spearman([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)
    assert golden_stats.kendall_tau_b([1, 1, 1], [1, 2, 3]) is None
    assert golden_stats.spearman([1, 1, 1], [1, 2, 3]) is None


def test_the_bootstrap_is_reproducible_under_the_fixed_seed():
    xs = [1, 2, 3, 4, 5, 6]
    ys = [2, 1, 4, 3, 6, 5]

    first = golden_stats.bootstrap_ci(xs, ys, golden_stats.kendall_tau_b)
    second = golden_stats.bootstrap_ci(xs, ys, golden_stats.kendall_tau_b)

    assert first == second, "seed 20260923 must reproduce the interval exactly"
    assert first is not None and first[0] <= first[1]


def test_dropping_a_sub_score_renormalises_the_weights_to_one():
    weights = golden_stats.sub_score_weights("w3")
    assert set(weights) == set(SUB_SCORE_NAMES)

    for dropped in SUB_SCORE_NAMES:
        scaled = golden_stats.renormalised(weights, dropped)
        assert dropped not in scaled
        assert sum(scaled.values()) == pytest.approx(1.0)


@pytest.mark.parametrize("weight_set", [W2, W3], ids=["w2", "w3"])
def test_the_ablation_recompute_equals_the_report_uncapped(weight_set):
    """Resume §5: with nothing dropped the recompute lands on the CSV's uncapped.

    The row is written by the runner's own row writer from a real `aggregate`
    report, so this compares the ablation against the scorer, not against itself.
    """
    sub_scores = {
        "skills": SubScore("skills", 0.6),
        "experience": SubScore("experience", 0.8),
        "title": SubScore("title", 0.5),
        "keywords": SubScore("keywords", 0.7),
    }
    report = aggregate(sub_scores, weight_set)
    analysis = SimpleNamespace(
        report={"score": report.to_dict(), "llm": {"calls": []}},
        weights_version=weight_set.version,
        cost_usd=Decimal("0"),
    )
    pair = SimpleNamespace(pair_id="1", profile="Ana", split="dev", lang="es")
    row = golden_run.csv_row(
        pair, analysis, SimpleNamespace(id="app-1"), "CV-1", "deadbeef", SUB_SCORE_NAMES
    )

    values = {name: row[name] for name in SUB_SCORE_NAMES}
    weights = golden_stats.sub_score_weights(weight_set.version)
    recomputed = golden_stats.ablation_total(values, weights, None)

    assert recomputed == pytest.approx(row["uncapped"], abs=1)


def synthetic_row(pair_id: str, uncapped: float, version: str, **extra: float) -> dict:
    values = {"skills": 0.5, "experience": 0.5, "title": 0.5, "keywords": 0.5}
    values.update(extra)
    return {
        "pair_id": pair_id,
        "profile": "Ana",
        "split": "dev",
        "lang": "es",
        "track": "CV-1",
        "weights_version": version,
        "score": uncapped,
        "uncapped": uncapped,
        "cap": "",
        **values,
        "skills_direct": "",
        "skills_transfer": "",
        "cost_usd": "0",
        "cached_calls": "0",
        "application_id": f"app-{pair_id}",
        "commit": "deadbeef",
    }


def test_the_report_states_the_split_the_seed_and_the_honesty_lines(
    tmp_path, monkeypatch, capsys
):
    repo = support.gitignored_dir(tmp_path)
    monkeypatch.setattr(golden_stats.golden_inputs, "DEFAULT_RUNS_DIR", repo / "runs")
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, score=1.0, score_direct_only=0.5, bucket="stretch"),
            support.row(2, score=2.0, score_direct_only=1.5, bucket="plausible"),
            support.row(3, score=3.0, score_direct_only=2.0, bucket="plausible"),
            support.row(4, score=4.0, score_direct_only=3.5, bucket="strong"),
        ],
    )
    w2_rows = [synthetic_row(str(index), float(index), "w2") for index in (1, 2, 3, 4)]
    w3_rows = [
        synthetic_row(str(index), float(index), "w3", skills_transfer=index / 10)
        for index in (1, 2, 3, 4)
    ]
    w2_csv = repo / "w2.csv"
    w3_csv = repo / "w3.csv"
    golden_run.write_csv(w2_csv, w2_rows, SUB_SCORE_NAMES)
    golden_run.write_csv(w3_csv, w3_rows, SUB_SCORE_NAMES)

    result = golden_stats.main(
        ["--runs", str(w2_csv), str(w3_csv), "--sheet", str(sheet)]
    )

    assert result == 0
    written = list((repo / "runs").glob("report-*.md"))
    assert len(written) == 1
    report = written[0].read_text(encoding="utf-8")
    assert "Split covered: dev" in report
    assert "seed 20260923" in report and "2,000 resamples" in report
    assert "uncapped vs score (primary)" in report and "tau-b" in report
    assert "1.000" in report, "perfect agreement on these synthetic rows is 1"
    assert "Transfer check (w3 only)" in report
    assert "w2 has no direct/transfer split" in report
    assert "| skills |" in report, "the ablation lists every sub-score"
    assert "not evidence of improvement" in report
    assert "rater_v2" in report and "F5.4.1" in report and "PRD §9" in report
    assert "wrote" in capsys.readouterr().out
