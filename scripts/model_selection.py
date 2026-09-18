"""Run the model-selection experiment (PRD §7, §9) and print the decision table.

The live run needs OPENROUTER_API_KEY and spends real money, so it reports progress
and the spend per candidate as it goes. It never touches OPENROUTER_MODEL: the
chosen model is the operator's decision, and this script only produces the evidence
for it.

    uv run python scripts/model_selection.py --pairs fixtures/golden

Paste the printed table and notes into `docs/model_selection.md`. The JSON written
beside it keeps the per-pair detail (levels, repeats, tokens, latency) that the
table has no room for.

Offline, the test suite exercises the same code path against the synthetic pairs
with a stubbed provider, so the harness is green in CI without a key.
"""

import argparse
import json
from pathlib import Path

from src.config import get_settings
from src.model_selection import (
    CANDIDATES,
    DEFAULT_REPEATS,
    DEFAULT_SEED,
    GLM_REFERENCE,
    Candidate,
    composition_notes,
    load_pairs,
    render_notes,
    render_table,
    report_to_json,
    run_experiment,
    verify_prices,
)


def candidate_selection(models: str) -> list[Candidate]:
    if not models:
        return list(CANDIDATES)
    wanted = {value.strip() for value in models.split(",") if value.strip()}
    chosen = [item for item in CANDIDATES if item.model in wanted or item.label in wanted]
    return chosen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Model-selection experiment (PRD §9)")
    parser.add_argument("--pairs", default="fixtures/golden", help="directory of golden *.toml")
    parser.add_argument("--out", default="fixtures/model_selection.json", help="JSON detail")
    parser.add_argument("--models", default="", help="comma-separated model ids or labels")
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--limit", type=int, default=0, help="first N pairs only (smoke run)")
    parser.add_argument(
        "--reference", action="store_true", help="also run the max-effort reference"
    )
    args = parser.parse_args(argv)

    if get_settings().openrouter_api_key is None:
        parser.error("OPENROUTER_API_KEY is not set; the live run needs it (see .env.example)")

    pairs = load_pairs(Path(args.pairs))
    if args.limit:
        pairs = pairs[: args.limit]
    candidates = candidate_selection(args.models)
    if not candidates:
        parser.error(f"no candidate matched {args.models!r}")
    if args.reference:
        candidates = [*candidates, GLM_REFERENCE]

    print(f"{len(pairs)} pairs · repeats {args.repeats} · seed {args.seed} · cache bypassed")
    for note in composition_notes(pairs):
        print(f"  ! {note}")
    for note in verify_prices(candidates):
        print(f"  ! {note}")
    print()

    reports = run_experiment(
        pairs, candidates, seed=args.seed, repeats=args.repeats, progress=print
    )

    print()
    print(render_table(reports, pairs=len(pairs)))
    print()
    print(render_notes(reports))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "seed": args.seed,
                "repeats": args.repeats,
                "pairs": [pair.id for pair in pairs],
                "models": [report_to_json(report) for report in reports],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
