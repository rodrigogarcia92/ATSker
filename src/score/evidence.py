"""Skills sub-score (weight 0.40): F5.5.1's basis-credited coverage.

Each requirement's level is multiplied by its evidence basis credit and the
requirement's weight class (must-have 0.75, nice-to-have 0.25), then normalised
over the total weight (PRD F5.5.1's formula). The credits are `w3`'s data and
come from the caller's weight set, never from here.

The sub-score is returned split (F5.5.1): the part from `direct` evidence and the
part from `equivalent` and `transferable` evidence. The transfer part is the part
a recruiter may not grant, so the user sees how much of the number rests on it —
and the two parts sum to the sub-score.

A requirement counts as *missing* at level 0 or 1 — the same rule F5.5 uses to
detect a gap, so the gap list and the score can never disagree.
"""

from collections.abc import Mapping, Sequence
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
    basis: str = "direct"


def _weight(entry: Level) -> float:
    return MUST_WEIGHT if entry.must_have else NICE_WEIGHT


def _coverage(levels: Sequence[Level]) -> float:
    if not levels:
        return 0.0
    return sum(entry.level for entry in levels) / (MAX_LEVEL * len(levels))


def evidence_coverage(
    levels: Sequence[Level], *, basis_credit: Mapping[str, float]
) -> SubScore:
    """`Σ weight(r) · credit(r) / Σ weight(r)`, and its direct/transfer split.

    `credit(r)` is `level(r) / 3 × basis_credit[basis(r)]` (F5.5.1). The split adds
    back up to the sub-score: `none` evidence contributes neither part, which is
    exactly what it contributes to the score.
    """
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
        detail.update({"direct": 0.0, "transfer": 0.0})
        return SubScore("evidence", 0.0, matched=[], missing=[], detail=detail)
    if must and not nice:
        detail["reason"] = "must_haves_only"
    elif nice and not must:
        detail["reason"] = "nice_to_haves_only"

    total_weight = sum(_weight(entry) for entry in levels)

    def part(bases: tuple[str, ...]) -> float:
        credited = sum(
            _weight(entry)
            * (entry.level / MAX_LEVEL)
            * basis_credit.get(entry.basis, 0.0)
            for entry in levels
            if entry.basis in bases
        )
        return credited / total_weight

    direct_part = part(("direct",))
    transfer_part = part(("equivalent", "transferable"))
    value = direct_part + transfer_part
    detail["direct"] = round(direct_part, 4)
    detail["transfer"] = round(transfer_part, 4)

    matched = [
        f"{entry.requirement} (L{entry.level}, {entry.basis})"
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
