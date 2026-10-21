"""How long an analysis takes, read from the reports themselves (PRD F12.4).

Every analysis stores its own timing since F12.4: the wall time from the first read
to the stored report, and each call's latency beside it. This script reads those
numbers instead of a stopwatch, so a claim about speed is a distribution over the
analyses actually run, not one spinner reading.

    uv run python scripts/latency_report.py
    uv run python scripts/latency_report.py --since 30d
    uv run python scripts/latency_report.py --since 7d --model anthropic/claude-haiku-5.5

Read-only: it opens the database the app uses (`DATABASE_URL`, as `llm_costs.py`
does), reads `applications.report` and prints. A report stored before F12.4 has no
timing and is counted as skipped, never guessed at. A cache hit made no provider
request, so its 0 ms is excluded from the latencies and counted as `cached`.
"""

import argparse
import math
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from scripts.llm_costs import parse_since  # noqa: E402
from src.db import session_scope  # noqa: E402
from src.models import Application  # noqa: E402

DEFAULT_SINCE = "7d"


def percentile(values: Sequence[float], fraction: float) -> float:
    """The nearest-rank percentile of `values`: the one at rank ceil(fraction × n).

    Ranks are 1-based, and there is no interpolation, so every number printed is a
    time something actually took. `values` must be non-empty and `fraction` in (0, 1].
    """
    if not values:
        raise ValueError("a percentile needs at least one value")
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[rank - 1]


def _seconds(milliseconds: float) -> str:
    return f"{milliseconds / 1000:.1f}s"


@dataclass
class _Purpose:
    """One purpose's calls in the window: the timed ones and the cache hits."""

    latencies: list[int] = field(default_factory=list)
    cached: int = 0


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _timing(report: object, model: str | None) -> tuple[int | None, dict[str, _Purpose]]:
    """One report's wall time and per-purpose latencies, restricted to `model`.

    The wall time is None — the report is skipped — when it has none, or when the
    model filter leaves no call of that model in it.
    """

    llm = report.get("llm") if isinstance(report, dict) else None
    calls = llm.get("calls") if isinstance(llm, dict) else None
    if not isinstance(calls, list):
        return None, {}
    purposes: dict[str, _Purpose] = {}
    matched = False
    for call in calls:
        if not isinstance(call, dict):
            continue
        if model is not None and call.get("model") != model:
            continue
        matched = True
        stats = purposes.setdefault(str(call.get("purpose") or "?"), _Purpose())
        latency = call.get("latency_ms")
        if call.get("cached"):
            stats.cached += 1
        elif _is_number(latency):
            stats.latencies.append(round(latency))
    wall = llm.get("wall_ms") if isinstance(llm, dict) else None
    if not matched or not _is_number(wall):
        return None, purposes
    return round(wall), purposes


def cmd_report(since_raw: str, model: str | None) -> int:
    """Print the wall and per-purpose distributions of the reports in the window."""
    since = parse_since(since_raw)
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(Application)
                .where(Application.created_at >= since)
                .order_by(Application.created_at, Application.id)
            )
        )

    walls: list[int] = []
    skipped = 0
    purposes: dict[str, _Purpose] = {}
    for row in rows:
        wall, call_stats = _timing(row.report, model)
        if wall is None:
            skipped += 1
            continue
        walls.append(wall)
        for purpose, stats in call_stats.items():
            merged = purposes.setdefault(purpose, _Purpose())
            merged.latencies.extend(stats.latencies)
            merged.cached += stats.cached

    if not walls:
        print("no timed analyses in that window")

    if walls:
        print(
            f"analyses: {len(walls)}   wall p50 {_seconds(percentile(walls, 0.50))}   "
            f"p95 {_seconds(percentile(walls, 0.95))}   max {_seconds(max(walls))}"
        )
        print(f"{'purpose':<18}{'n':>4}{'cached':>8}{'p50':>9}{'p95':>9}")
        for purpose in sorted(purposes):
            stats = purposes[purpose]
            p50 = _seconds(percentile(stats.latencies, 0.50)) if stats.latencies else "–"
            p95 = _seconds(percentile(stats.latencies, 0.95)) if stats.latencies else "–"
            print(f"{purpose:<18}{len(stats.latencies):>4}{stats.cached:>8}{p50:>9}{p95:>9}")
    print(f"skipped (no timing): {skipped}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Response time per analysis and per purpose, read from the stored reports. "
            "Read-only; reports stored before F12.4 have no timing and are counted."
        )
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"ISO date or timestamp, or a window (2d, 48h); default {DEFAULT_SINCE}",
    )
    parser.add_argument("--model", default=None, help="only analyses that used this model")
    args = parser.parse_args(argv)
    return cmd_report(args.since, args.model)


if __name__ == "__main__":
    raise SystemExit(main())
