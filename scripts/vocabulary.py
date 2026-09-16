"""Vocabulary administration: seed, review, promote (PRD F3).

Alias promotion is the only supported way the vocabulary grows, and it is a human
decision: this script shows the unmapped-term log and lets the operator attach a
term to a canonical skill.

    uv run python scripts/vocabulary.py seed
    uv run python scripts/vocabulary.py unmapped
    uv run python scripts/vocabulary.py promote --term "powerbi" --canonical "power bi"
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import session_scope  # noqa: E402
from src.vocabulary import list_unmapped, promote_alias, seed_vocabulary  # noqa: E402

SEED_FILE = Path(__file__).resolve().parents[1] / "src" / "normalize" / "skills_seed.json"


def cmd_seed() -> int:
    entries = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    with session_scope() as session:
        result = seed_vocabulary(session, entries)
    print(
        f"seeded {SEED_FILE.name}: {result['created']} created, "
        f"{result['enriched']} enriched, {result['total']} canonicals in the database"
    )
    return 0


def cmd_unmapped() -> int:
    with session_scope() as session:
        terms = list_unmapped(session)
        if not terms:
            print("no unmapped terms")
            return 0
        for term in terms:
            print(f"{term.seen_count:>4}  {term.status:<9} {term.term}")
    return 0


def cmd_promote(term: str, canonical: str) -> int:
    with session_scope() as session:
        skill = promote_alias(session, canonical, term)
        print(f"{term!r} now maps to {skill.canonical!r} ({len(skill.aliases)} aliases)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ATSker vocabulary administration.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed", help="apply skills_seed.json (idempotent)")
    sub.add_parser("unmapped", help="list terms awaiting a decision")
    promote = sub.add_parser("promote", help="attach a term to a canonical skill")
    promote.add_argument("--term", required=True)
    promote.add_argument("--canonical", required=True)

    args = parser.parse_args()
    if args.command == "seed":
        return cmd_seed()
    if args.command == "unmapped":
        return cmd_unmapped()
    return cmd_promote(args.term, args.canonical)


if __name__ == "__main__":
    raise SystemExit(main())
