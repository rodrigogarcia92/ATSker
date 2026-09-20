"""What the model calls cost, without a SQL client (PRD 7).

Every `llm_calls` row is a call that was actually paid for. A cache hit writes no
row — the stored response *is* the answer the hit returns — so there is no "cached"
column to print: every row listed here is a fresh, billed call, and the cache is
what keeps the list short.

    uv run python scripts/llm_costs.py
    uv run python scripts/llm_costs.py --since 2026-09-19
    uv run python scripts/llm_costs.py --since 2d --limit 10
"""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402

from src.db import session_scope  # noqa: E402
from src.models import LlmCall  # noqa: E402

HEADER = (
    f"{'created':<17} {'purpose':<18} {'model':<26} {'prompt version':<22} "
    f"{'tokens':>15}  {'cost':>11}"
)


def parse_since(raw: str) -> datetime:
    """A date, a timestamp, or a relative window such as `2d` or `48h`."""
    text = raw.strip()
    if text.endswith("d") and text[:-1].isdigit():
        return datetime.now(UTC) - timedelta(days=int(text[:-1]))
    if text.endswith("h") and text[:-1].isdigit():
        return datetime.now(UTC) - timedelta(hours=int(text[:-1]))
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


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
        tokens = f"{row.prompt_tokens} + {row.completion_tokens}"
        print(
            f"{row.created_at:%Y-%m-%d %H:%M} {row.purpose:<18} {row.model:<26} "
            f"{row.prompt_version:<22} {tokens:>15}  ${row.cost_usd:>10.6f}"
        )

    shown = len(rows)
    tail = f" (showing the most recent {shown})" if shown < count else ""
    calls = "call" if count == 1 else "calls"
    print(f"total: ${total:.6f} over {count} {calls}{tail}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ATSker model-call ledger.")
    parser.add_argument(
        "--since",
        default=None,
        help="ISO date or timestamp (2026-09-19), or a window (2d, 48h)",
    )
    parser.add_argument("--limit", type=int, default=50, help="rows to print (default 50)")
    args = parser.parse_args()
    return cmd_list(args.since, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
