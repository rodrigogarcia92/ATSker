"""Agreement statistics for the golden-set runs (queue A.4, resume §5).

Hand-computed values below are worked out in the test docstrings from the
definitions in `golden_stats`'s module docstring — ties included, because the
rater's scores tie and the tie correction is the whole point of tau-b.
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import golden_run, golden_stats
from src.score.aggregate import SubScore, aggregate
from src.score.weights import W2, W3, W4
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


def synthetic_row(
    pair_id: str,
    uncapped: float,
    version: str,
    *,
    split: str = "dev",
    vocabulary_hash: str = "",
    **extra: object,
) -> dict:
    values = {"skills": 0.5, "experience": 0.5, "title": 0.5, "keywords": 0.5}
    values.update(extra)
    skills_transfer = values.pop("skills_transfer", "")
    return {
        "pair_id": pair_id,
        "profile": "Ana",
        "split": split,
        "lang": "es",
        "track": "CV-1",
        "weights_version": version,
        "vocabulary_hash": vocabulary_hash,
        "score": uncapped,
        "uncapped": uncapped,
        "cap": "",
        **values,
        "skills_direct": "",
        "skills_transfer": skills_transfer,
        "cost_usd": "0",
        "cached_calls": "0",
        "model": "test/model-v1",
        "reasoning_effort": "medium",
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
            support.row(1, score=1.0, score_direct_only=0.5, bucket="stretch", rater="ana"),
            support.row(2, score=2.0, score_direct_only=1.5, bucket="plausible", rater="ana"),
            support.row(3, score=3.0, score_direct_only=2.0, bucket="plausible", rater="ana"),
            support.row(4, score=4.0, score_direct_only=3.5, bucket="strong", rater="ana"),
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
    assert "w2 has no direct/transfer split" in report
    assert "| skills |" in report, "the ablation lists every sub-score"
    assert "not evidence of improvement" in report
    assert "ana" in report and "rater_v2" not in report, "the rater comes from the sheet"
    assert "F5.4.1" in report and "PRD §9" in report
    assert "wrote" in capsys.readouterr().out


def write_run(repo, name: str, rows: list[dict]) -> Path:
    path = repo / name
    golden_run.write_csv(path, rows, SUB_SCORE_NAMES)
    return path


def read_report(repo) -> str:
    return sorted((repo / "runs").glob("report-*.md"))[0].read_text(encoding="utf-8")


def four_pairs(tmp_path) -> Path:
    return support.write_sheet(
        tmp_path / "sheet.xlsx",
        [support.row(index, score=float(index)) for index in (1, 2, 3, 4)],
    )


def test_one_run_alone_produces_a_report_with_no_between_run_comparison(
    tmp_path, monkeypatch, capsys
):
    """A.6: `--runs` takes one or more. One run has nothing to compare and must not
    pretend otherwise — no vocabulary warning, one run section."""
    repo = support.gitignored_dir(tmp_path)
    monkeypatch.setattr(golden_stats.golden_inputs, "DEFAULT_RUNS_DIR", repo / "runs")
    sheet = four_pairs(tmp_path)
    rows = [
        synthetic_row(str(index), float(index), "w4", vocabulary_hash="sha256:a")
        for index in (1, 2, 3, 4)
    ]

    run = write_run(repo, "w4.csv", rows)
    assert golden_stats.main(["--runs", str(run), "--sheet", str(sheet)]) == 0

    report = read_report(repo)
    assert report.count("## Run ") == 1
    assert "Warning" not in report
    assert "- w4.csv: sha256:a" in report
    assert "wrote" in capsys.readouterr().out


def test_two_runs_on_different_vocabularies_say_so(tmp_path, monkeypatch):
    """F3.1: a score difference may be the words rather than the scorer."""
    repo = support.gitignored_dir(tmp_path)
    monkeypatch.setattr(golden_stats.golden_inputs, "DEFAULT_RUNS_DIR", repo / "runs")
    sheet = four_pairs(tmp_path)
    first = write_run(
        repo,
        "w3.csv",
        [synthetic_row(str(i), float(i), "w3", vocabulary_hash="sha256:a") for i in (1, 2, 3, 4)],
    )
    second = write_run(
        repo,
        "w4.csv",
        [synthetic_row(str(i), float(i), "w4", vocabulary_hash="sha256:b") for i in (1, 2, 3, 4)],
    )

    assert golden_stats.main(["--runs", str(first), str(second), "--sheet", str(sheet)]) == 0

    report = read_report(repo)
    assert "- w3.csv: sha256:a" in report and "- w4.csv: sha256:b" in report
    assert "different vocabularies" in report


def test_w4_rows_ablate_with_w4s_own_weights(tmp_path, monkeypatch):
    """A.6: `w4` is a weight set the ablation can renormalise, not an error."""
    weights = golden_stats.sub_score_weights("w4")
    assert weights == {
        "skills": W4.skills,
        "experience": W4.experience,
        "title": W4.title,
        "keywords": W4.keywords,
    }

    repo = support.gitignored_dir(tmp_path)
    monkeypatch.setattr(golden_stats.golden_inputs, "DEFAULT_RUNS_DIR", repo / "runs")
    sheet = four_pairs(tmp_path)
    rows = [
        synthetic_row(str(index), float(index), "w4", skills=index / 10) for index in (1, 2, 3, 4)
    ]

    run = write_run(repo, "w4.csv", rows)
    assert golden_stats.main(["--runs", str(run), "--sheet", str(sheet)]) == 0

    report = read_report(repo)
    assert "weights w4" in report
    for name in SUB_SCORE_NAMES:
        assert f"| {name} |" in report
    assert "### test" not in report, "a sealed split gets no section"


def test_with_include_test_the_dev_and_test_tables_are_separate(tmp_path, monkeypatch):
    """A.6: never pooled. Each split is its own table with its own n, dev first."""
    repo = support.gitignored_dir(tmp_path)
    monkeypatch.setattr(golden_stats.golden_inputs, "DEFAULT_RUNS_DIR", repo / "runs")
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, score=1.0),
            support.row(2, score=2.0),
            support.row(3, score=3.0, split="test"),
        ],
    )
    rows = [
        synthetic_row("1", 1.0, "w4", skills=0.1),
        synthetic_row("2", 2.0, "w4", skills=0.2),
        synthetic_row("3", 3.0, "w4", skills=0.3, split="test"),
    ]
    run = write_run(repo, "w4.csv", rows)

    assert golden_stats.main(
        ["--runs", str(run), "--sheet", str(sheet), "--include-test"]
    ) == 0

    report = read_report(repo)
    assert report.index("### dev") < report.index("### test")
    dev = report.split("### dev", 1)[1].split("### test", 1)[0]
    test = report.split("### test", 1)[1]
    assert "| skills | undefined | 2 |" in dev, "the dev table counts dev rows"
    assert "| skills | undefined | 1 |" in test, "the test table counts test rows"
