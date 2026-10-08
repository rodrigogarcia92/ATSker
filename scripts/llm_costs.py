"""What the model calls cost, without a SQL client (PRD 7).

Every `llm_calls` row is a call that was actually paid for. A cache hit writes no
row — the stored response *is* the answer the hit returns — so there is no "cached"
column to print: every row listed here is a fresh, billed call, and the cache is
what keeps the list short.

    uv run python scripts/llm_costs.py
    uv run python scripts/llm_costs.py --since 2026-09-19
    uv run python scripts/llm_costs.py --since 2d --limit 10

`summary` totals the ledger by model and purpose — what a model trial needs to compare two
models. The ledger has no application id, so a cost *per analysis* cannot be computed from it
and is not printed.

    uv run python scripts/llm_costs.py summary --since 7d
    uv run python scripts/llm_costs.py summary --since 7d --by purpose

`purge` is the operator's way out of a bad answer that is already stored (F2.3.1):
a row written before the degeneracy check existed is served back free and forever,
so it has to be excluded from the cache by hand. It marks rows rather than deleting
them — the ledger keeps the cost (decision 21) — and it prints what it would touch
unless `--confirm` says otherwise.

    uv run python scripts/llm_costs.py purge --hash <sha256>
    uv run python scripts/llm_costs.py purge --hash <sha256> --confirm
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decimal import Decimal  # noqa: E402

from sqlalchemy import func, select  # noqa: E402

from src.db import session_scope  # noqa: E402
from src.models import LlmCall  # noqa: E402

HEADER = (
    f"{'created':<17} {'purpose':<18} {'model':<26} {'prompt version':<22} "
    f"{'tokens':>15}  {'cost':>11}"
)

SUMMARY_HEADER = (
    f"{'model':<26} {'purpose':<18} {'calls':>6} {'purged':>6} "
    f"{'prompt tok':>11} {'compl tok':>10} {'cost':>12} {'avg/call':>11}"
)

# Shown beside a row the cache will not serve again.
DEGENERATE_MARK = "purged"


def parse_since(raw: str) -> datetime:
    """A date, a timestamp, or a relative window such as `2d` or `48h`."""
    text = raw.strip()
    if text.endswith("d") and text[:-1].isdigit():
        return datetime.now(UTC) - timedelta(days=int(text[:-1]))
    if text.endswith("h") and text[:-1].isdigit():
        return datetime.now(UTC) - timedelta(hours=int(text[:-1]))
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _row_line(row: LlmCall) -> str:
    tokens = f"{row.prompt_tokens} + {row.completion_tokens}"
    mark = f"  [{DEGENERATE_MARK}]" if row.degenerate else ""
    return (
        f"{row.created_at:%Y-%m-%d %H:%M} {row.purpose:<18} {row.model:<26} "
        f"{row.prompt_version:<22} {tokens:>15}  ${row.cost_usd:>10.6f}{mark}"
    )


def cmd_list(since_raw: str | None, limit: int) -> int:
    since = parse_since(since_raw) if since_raw else None
    criteria = [] if since is None else [LlmCall.created_at >= since]
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(LlmCall)
                .where(*criteria)
                .order_by(LlmCall.created_at.desc(), LlmCall.id.desc())
                .limit(limit)
            )
        )
        count, total = session.execute(
            select(func.count(LlmCall.id), func.coalesce(func.sum(LlmCall.cost_usd), 0)).where(
                *criteria
            )
        ).one()

    if not rows:
        print("no model calls in that window")
        return 0

    print(HEADER)
    for row in rows:
        print(_row_line(row))

    shown = len(rows)
    tail = f" (showing the most recent {shown})" if shown < count else ""
    calls = "call" if count == 1 else "calls"
    print(f"total: ${total:.6f} over {count} {calls}{tail}")
    purged = sum(1 for row in rows if row.degenerate)
    if purged:
        print(f"{purged} of them marked [{DEGENERATE_MARK}]: billed, never served from the cache")
    return 0


def _money(value: Decimal) -> str:
    return f"${value:.6f}"


@dataclass
class _Totals:
    calls: int = 0
    degenerate: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost: Decimal = Decimal(0)

    def add(self, prompt: int, completion: int, cost: Decimal, degenerate: bool) -> None:
        self.calls += 1
        self.degenerate += 1 if degenerate else 0
        self.prompt_tokens += prompt or 0
        self.completion_tokens += completion or 0
        self.cost += cost or Decimal(0)

    def line(self, first: str, second: str) -> str:
        average = self.cost / self.calls if self.calls else Decimal(0)
        return (
            f"{first:<26} {second:<18} {self.calls:>6} {self.degenerate:>6} "
            f"{self.prompt_tokens:>11} {self.completion_tokens:>10} "
            f"{_money(self.cost):>12} {_money(average):>11}"
        )


def cmd_summary(since_raw: str, by: str = "model") -> int:
    """Totals per (model, purpose), then per model (or per purpose with `--by purpose`).

    Reads only counts, tokens, cost and the degenerate flag: never `response_json`, which can
    hold personal data, and never a hash. The ledger has no application id, so the cost per
    analysis is deliberately not derived here.
    """
    since = parse_since(since_raw)
    with session_scope() as session:
        rows = session.execute(
            select(
                LlmCall.model,
                LlmCall.purpose,
                LlmCall.prompt_tokens,
                LlmCall.completion_tokens,
                LlmCall.cost_usd,
                LlmCall.degenerate,
            ).where(LlmCall.created_at >= since)
        ).all()
    if not rows:
        print("no model calls in that window")
        return 0

    groups: dict[tuple[str, str], _Totals] = {}
    for model, purpose, prompt, completion, cost, degenerate in rows:
        groups.setdefault((model, purpose), _Totals()).add(
            prompt, completion, cost, bool(degenerate)
        )
    # The first key is what the rows are grouped under and what gets a total.
    first = 0 if by == "model" else 1
    ordered = sorted(groups, key=lambda key: (key[first], key[1 - first]))
    print(SUMMARY_HEADER)
    for key in ordered:
        print(groups[key].line(key[0], key[1]))
    print()
    totals: dict[str, _Totals] = {}
    for key in ordered:
        bucket = totals.setdefault(key[first], _Totals())
        group = groups[key]
        bucket.calls += group.calls
        bucket.degenerate += group.degenerate
        bucket.prompt_tokens += group.prompt_tokens
        bucket.completion_tokens += group.completion_tokens
        bucket.cost += group.cost
    for name, bucket in totals.items():
        label = "(all purposes)" if by == "model" else "(all models)"
        print(bucket.line(name, label) if by == "model" else bucket.line(label, name))
    return 0


def cmd_purge(content_hash: str, confirm: bool) -> int:
    """Exclude the rows for one content hash from the cache, keeping their cost.

    The degeneracy check cannot be retrofitted onto rows already written, so this is
    the operator's path for an answer that is already stored (F2.3.1). Dry by default:
    it prints the rows it would mark and writes nothing until `--confirm`.
    """
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(LlmCall).where(LlmCall.input_hash == content_hash).order_by(LlmCall.id)
            )
        )
        if not rows:
            print(f"no call matches {content_hash}")
            return 1

        print(HEADER)
        for row in rows:
            print(_row_line(row))
        already = [row for row in rows if row.degenerate]
        print(
            f"{len(rows)} row(s) for {content_hash}; "
            f"{len(already)} already marked [{DEGENERATE_MARK}]"
        )
        if not confirm:
            print("dry run: nothing written. Re-run with --confirm to mark them.")
            return 0

        for row in rows:
            row.degenerate = True
        print(f"marked {len(rows)} row(s) [{DEGENERATE_MARK}]: the cache will not serve them again")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "summary":
        parser = argparse.ArgumentParser(
            prog="llm_costs.py summary",
            description=(
                "Calls, purged rows, tokens and cost per model and purpose, then a total per "
                "model. The ledger has no application id, so cost per analysis is not printed."
            ),
        )
        parser.add_argument(
            "--since",
            required=True,
            help="ISO date or timestamp (2026-09-19), or a window (2d, 48h)",
        )
        parser.add_argument(
            "--by",
            choices=("model", "purpose"),
            default="model",
            help="group the rows, and total them, by model (default) or by purpose",
        )
        args = parser.parse_args(argv[1:])
        return cmd_summary(args.since, args.by)
    if argv and argv[0] == "purge":
        parser = argparse.ArgumentParser(prog="llm_costs.py purge", description="Purge one hash.")
        parser.add_argument("--hash", dest="content_hash", required=True, help="hash to purge")
        parser.add_argument(
            "--confirm", action="store_true", help="write the change (default: dry run)"
        )
        args = parser.parse_args(argv[1:])
        return cmd_purge(args.content_hash, args.confirm)

    parser = argparse.ArgumentParser(description="ATSker model-call ledger.")
    parser.add_argument(
        "--since",
        default=None,
        help="ISO date or timestamp (2026-09-19), or a window (2d, 48h)",
    )
    parser.add_argument("--limit", type=int, default=50, help="rows to print (default 50)")
    args = parser.parse_args(argv)
    return cmd_list(args.since, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
