"""Agreement statistics for the golden-set runs (queue A.4).

The operator's question is whether `w3` tracks the rater's judgement better than
`w2`, and with about twelve dev pairs an honest answer needs intervals beside
the coefficients: the report says so in as many words, every time. Pure Python
and the standard library; the weights come from `src.score` (imported from the
working directory like the runner does), so the ablation can only renormalise
what the scorers themselves declared. Run it from the main checkout — that is
where `W3` lives (queue A.6).

Definitions, so the numbers can be checked by hand:

- Kendall's tau-b: (C − D) / sqrt((C + D + T)(C + D + U)) over pairs, where T
  and U are pairs tied in one variable only; pairs tied in both are excluded.
- Spearman's rho: Pearson correlation of average ranks (ties share the mean of
  the ranks they span).
- Intervals: percentile bootstrap, 2,000 resamples of pairs with replacement,
  seed 20260923 (each statistic reseeds, so any line reproduces on its own).
  Resamples where the statistic is undefined are discarded.
- The ablation recomputes each pair's total on the uncapped scale —
  `100 * sum(w_i * v_i) / sum(w_i)` over the remaining sub-scores — with the
  weights of the run's own `weights_version`, then reports tau-b against the
  rater's `score` for each dropped sub-score.

Output: `fixtures/golden/runs/report-<YYYYMMDD-HHMM>.md`, printed as well.
The report is only written where `git check-ignore` matches (queue A.3 step 5).
"""

import argparse
import csv
import math
import random
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path.cwd()))

import golden_inputs  # noqa: E402

from src.score.aggregate import SUB_SCORES  # noqa: E402
from src.score.weights import W2, W3  # noqa: E402

SEED = 20260923
RESAMPLES = 2000
BUCKET_ORDER = {"stretch": 0, "plausible": 1, "strong": 2}
WEIGHT_SETS = {"w2": W2, "w3": W3}

# (label, CSV column, sheet column, rho reported too) — the queue's primary
# comparison first, then capped vs score, each scale vs score_direct_only, and
# tau-b against the ordinal bucket.
COMPARISONS = (
    ("uncapped vs score (primary)", "uncapped", "score", True),
    ("capped vs score", "score", "score", True),
    ("uncapped vs score_direct_only", "uncapped", "score_direct_only", True),
    ("capped vs score_direct_only", "score", "score_direct_only", True),
    ("uncapped vs bucket (ordinal)", "uncapped", "bucket", False),
)


class StatsError(Exception):
    """A run file or the sheet cannot support the statistics asked for."""


def average_ranks(values: list[float]) -> list[float]:
    """1-based ranks; ties share the mean of the ranks they span."""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        shared = (start + end) / 2 + 1
        for position in range(start, end + 1):
            ranks[order[position]] = shared
        start = end + 1
    return ranks


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    count = len(xs)
    if count < 2:
        return None
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    cross = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True))
    spread_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    spread_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if spread_x == 0 or spread_y == 0:
        return None
    return cross / (spread_x * spread_y)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    """Average ranks for ties, then Pearson."""
    return _pearson(average_ranks(xs), average_ranks(ys))


def kendall_tau_b(xs: list[float], ys: list[float]) -> float | None:
    """Tie-corrected tau-b; pairs tied in both variables are excluded."""
    count = len(xs)
    if count < 2:
        return None
    concordant = discordant = tied_x = tied_y = 0
    for left in range(count):
        for right in range(left + 1, count):
            step_x = (xs[left] > xs[right]) - (xs[left] < xs[right])
            step_y = (ys[left] > ys[right]) - (ys[left] < ys[right])
            if step_x == 0 and step_y == 0:
                continue
            if step_x == 0:
                tied_x += 1
            elif step_y == 0:
                tied_y += 1
            elif step_x == step_y:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + tied_x) * (concordant + discordant + tied_y)
    )
    if denominator == 0:
        return None
    return (concordant - discordant) / denominator


def bootstrap_ci(
    xs: list[float],
    ys: list[float],
    statistic,
    *,
    resamples: int = RESAMPLES,
    seed: int = SEED,
) -> tuple[float, float] | None:
    """Percentile 95% interval over resampled pairs; undefined draws are dropped."""
    count = len(xs)
    if count < 2:
        return None
    rng = random.Random(seed)
    drawn: list[float] = []
    for _ in range(resamples):
        picks = [rng.randrange(count) for _ in range(count)]
        value = statistic([xs[index] for index in picks], [ys[index] for index in picks])
        if value is not None:
            drawn.append(value)
    if not drawn:
        return None
    drawn.sort()
    return (drawn[int(0.025 * (len(drawn) - 1))], drawn[int(0.975 * (len(drawn) - 1))])


def sub_score_weights(weights_version: str) -> dict[str, float]:
    """The four sub-score weights of the version the rows name (resume §5)."""
    weight_set = WEIGHT_SETS.get(weights_version)
    if weight_set is None:
        raise StatsError(f"unknown weights_version {weights_version!r} in the run file")
    return {name: getattr(weight_set, name) for name in SUB_SCORES}


def renormalised(weights: dict[str, float], drop: str | None) -> dict[str, float]:
    """The remaining weights scaled back to sum to 1."""
    remaining = {name: value for name, value in weights.items() if name != drop}
    total = sum(remaining.values())
    return {name: value / total for name, value in remaining.items()}


def ablation_total(values: dict[str, float], weights: dict[str, float], drop: str | None) -> float:
    """`100 * sum(w_i * v_i) / sum(w_i)` over the sub-scores left (resume §5)."""
    scaled = renormalised(weights, drop)
    return 100 * sum(weight * values[name] for name, weight in scaled.items())


def read_run(path: Path) -> tuple[list[dict[str, str]], tuple[str, ...]]:
    """The run's rows and its sub-score column names. Comment lines are skipped."""
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise StatsError(f"run file not found: {path}") from exc
    reader = csv.DictReader([line for line in raw if not line.startswith("#")])
    header = reader.fieldnames or []
    fixed = set(golden_inputs.COLUMNS_BEFORE_SUB_SCORES) | set(
        golden_inputs.COLUMNS_AFTER_SUB_SCORES
    )
    sub_names = tuple(name for name in header if name not in fixed)
    missing = [
        name
        for name in ("pair_id", "split", "score", "uncapped", "weights_version", "skills_transfer")
        if name not in header
    ]
    if missing:
        raise StatsError(f"{path}: run file is missing columns: {', '.join(missing)}")
    if not set(SUB_SCORES) <= set(sub_names):
        raise StatsError(f"{path}: run file is missing sub-score columns")
    return list(reader), sub_names


def _number(row: dict[str, str], name: str) -> float | None:
    raw = (row.get(name) or "").strip()
    return float(raw) if raw else None


def _format(value: float | None) -> str:
    return "undefined" if value is None else f"{value:.3f}"


def _interval(bounds: tuple[float, float] | None) -> str:
    return "[-, -]" if bounds is None else f"[{bounds[0]:.3f}, {bounds[1]:.3f}]"


def _paired(
    rows: list[dict[str, str]],
    sheet: dict[str, golden_inputs.Pair],
    run_column: str,
    rater_column: str,
) -> tuple[list[float], list[float]]:
    """Paired values, in row order; a pair missing either side sits that one out."""
    xs: list[float] = []
    ys: list[float] = []
    for row in rows:
        run_value = _number(row, run_column)
        pair = sheet[row["pair_id"]]
        if rater_column == "bucket":
            if pair.bucket not in BUCKET_ORDER:
                raise StatsError(
                    f"pair {pair.pair_id}: unknown bucket {pair.bucket!r} "
                    f"(expected one of {', '.join(sorted(BUCKET_ORDER))})"
                )
            rater_value = float(BUCKET_ORDER[pair.bucket])
        else:
            rater_value = getattr(pair, rater_column)
        if run_value is None or rater_value is None:
            continue
        xs.append(run_value)
        ys.append(rater_value)
    return xs, ys


def _comparison_lines(
    label: str,
    xs: list[float],
    ys: list[float],
    with_rho: bool,
) -> list[str]:
    rows = []
    count = len(xs)
    tau = kendall_tau_b(xs, ys)
    tau_bounds = _interval(bootstrap_ci(xs, ys, kendall_tau_b))
    rows.append(f"| {label} | tau-b | {_format(tau)} | {tau_bounds} | {count} |")
    if with_rho:
        rho = spearman(xs, ys)
        rho_bounds = _interval(bootstrap_ci(xs, ys, spearman))
        rows.append(f"| {label} | rho | {_format(rho)} | {rho_bounds} | {count} |")
    return rows


def build_report(run_paths: list[Path], sheet_path: Path, *, include_test: bool) -> str:
    sheet = {
        pair.pair_id: pair for pair in golden_inputs.read_pairs(sheet_path, include_test=True)
    }
    runs = [(path, *read_run(path)) for path in run_paths]

    lines = [
        f"# Golden-set agreement report {datetime.now().isoformat(timespec='minutes')}",
        "",
        "Statistics: Kendall's tau-b (tie-corrected) and Spearman's rho (average "
        "ranks for ties), each with a percentile bootstrap 95% interval — "
        f"{RESAMPLES:,} resamples of pairs, seed {SEED}. Resamples where the "
        "statistic is undefined are discarded.",
        "",
    ]

    covered: set[str] = set()
    for _path, rows, _ in runs:
        covered.update(row["split"] for row in rows if row["split"] == "test" or include_test)
    covered.add("dev")
    lines.insert(
        3,
        f"Split covered: {' + '.join(sorted(covered))} "
        f"(test rows {'included' if include_test else 'excluded'} unless present).",
    )

    for path, rows, _ in runs:
        in_scope = [
            row
            for row in rows
            if row["split"] == "dev" or (include_test and row["split"] == "test")
        ]
        if not in_scope:
            raise StatsError(f"{path}: no rows in the covered split")
        for row in in_scope:
            if row["pair_id"] not in sheet:
                raise StatsError(f"{path}: pair {row['pair_id']} is not in the sheet")
        version = in_scope[0]["weights_version"]
        weights = sub_score_weights(version)
        lines += [
            f"## Run {path.name} (commit {in_scope[0]['commit']}, weights {version})",
            "",
            "| comparison | statistic | value | 95% interval | n |",
            "|---|---|---|---|---|",
        ]
        for label, run_column, rater_column, with_rho in COMPARISONS:
            xs, ys = _paired(in_scope, sheet, run_column, rater_column)
            lines += _comparison_lines(label, xs, ys, with_rho)

        # The transfer check is w3's: w2 computes no split, so its column is blank.
        if version == "w3":
            xs = []
            ys = []
            for row in in_scope:
                transfer = _number(row, "skills_transfer")
                pair = sheet[row["pair_id"]]
                if transfer is None or pair.score is None or pair.score_direct_only is None:
                    continue
                xs.append(transfer)
                ys.append(pair.score - pair.score_direct_only)
            lines += [
                "",
                "**Transfer check (w3 only)** — Spearman between `skills_transfer` and "
                "`score − score_direct_only`: "
                f"{_format(spearman(xs, ys))} "
                f"{_interval(bootstrap_ci(xs, ys, spearman))} (n = {len(xs)}).",
            ]
        else:
            lines += [
                "",
                "**Transfer check** — not computed: w2 has no direct/transfer split "
                "(the column is blank by construction).",
            ]

        lines += [
            "",
            "**Ablation** — total recomputed with one sub-score dropped and the "
            "remaining weights renormalised to sum to 1; tau-b against the rater's "
            "`score`:",
            "",
            "| dropped | tau-b vs score | n |",
            "|---|---|---|",
        ]
        for name in SUB_SCORES:
            xs = []
            ys = []
            for row in in_scope:
                pair = sheet[row["pair_id"]]
                values = {column: _number(row, column) for column in SUB_SCORES}
                if pair.score is None or any(value is None for value in values.values()):
                    continue
                xs.append(ablation_total(values, weights, name))
                ys.append(pair.score)
            lines.append(f"| {name} | {_format(kendall_tau_b(xs, ys))} | {len(xs)} |")
        lines.append("")

    lines += [
        "## Honesty",
        "",
        "- Every statistic states its n. With n ≈ 12 these intervals are wide: a "
        "difference between w2 and w3 whose intervals overlap is not evidence of "
        "improvement.",
        "- Agreement with `rater_v2` partly reflects the rubric it shares with F5.4.1 "
        "(PRD §9).",
        "",
    ]
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agreement statistics for golden-set runs.")
    parser.add_argument("--runs", nargs=2, required=True, type=Path, metavar="CSV")
    parser.add_argument("--sheet", type=Path, default=golden_inputs.DEFAULT_SHEET)
    parser.add_argument("--include-test", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    report_path = golden_inputs.DEFAULT_RUNS_DIR / f"report-{stamp}.md"
    if not golden_inputs.output_is_ignored(report_path):
        print(f"refusing to write outside a gitignored path: {report_path}")
        return 2
    try:
        report = build_report(args.runs, args.sheet, include_test=args.include_test)
    except (StatsError, golden_inputs.SheetError) as failure:
        print(str(failure))
        return 2
    report_path.write_text(report, encoding="utf-8")
    print(report)
    print(f"wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
