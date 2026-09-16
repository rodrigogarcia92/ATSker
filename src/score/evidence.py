"""Evidence coverage (weight 0.35): `Σ(level) / (3 × n)`, must-haves weighted heavier.

Must-haves carry 0.75 of this sub-score and nice-to-haves 0.25, per PRD F4.4. When a
posting has only one of the two groups, the weight is not redistributed by guesswork:
the missing group is reported in the detail and the present group is scored alone.

A requirement counts as *missing* at level 0 or 1 — the same rule F5 uses to detect a
gap, so the gap list and the score can never disagree.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from src.score.aggregate import SubScore

MUST_WEIGHT = 0.75
NICE_WEIGHT = 0.25
MAX_LEVEL = 3
EVIDENCE_THRESHOLD = 2  # level 2 or 3 is evidence; 0 and 1 are a gap


@dataclass(frozen=True)
class Level:
    requirement: str
    level: int
    must_have: bool


def _coverage(levels: Sequence[Level]) -> float:
    if not levels:
        return 0.0
    return sum(entry.level for entry in levels) / (MAX_LEVEL * len(levels))


def evidence_coverage(levels: Sequence[Level]) -> SubScore:
    must = [entry for entry in levels if entry.must_have]
    nice = [entry for entry in levels if not entry.must_have]
    detail: dict[str, object] = {
        "must_have_count": len(must),
        "nice_to_have_count": len(nice),
        "must_coverage": round(_coverage(must), 4),
        "nice_coverage": round(_coverage(nice), 4),
    }

    if not must and not nice:
        detail["reason"] = "no_requirements"
        return SubScore("evidence", 0.0, matched=[], missing=[], detail=detail)

    if must and nice:
        value = MUST_WEIGHT * _coverage(must) + NICE_WEIGHT * _coverage(nice)
    elif must:
        detail["reason"] = "must_haves_only"
        value = _coverage(must)
    else:
        detail["reason"] = "nice_to_haves_only"
        value = _coverage(nice)

    matched = [
        f"{entry.requirement} (L{entry.level})"
        for entry in levels
        if entry.level >= EVIDENCE_THRESHOLD
    ]
    missing = [
        f"{entry.requirement} (L{entry.level})"
        for entry in levels
        if entry.level < EVIDENCE_THRESHOLD
    ]
    return SubScore(
        name="evidence",
        value=round(value, 4),
        matched=matched,
        missing=missing,
        detail=detail,
    )
