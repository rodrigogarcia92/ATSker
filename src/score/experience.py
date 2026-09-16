"""Experience (weight 0.20): years actually held against years required.

Concurrent roles are merged before counting, so two overlapping jobs cannot add up
to more experience than the calendar holds. The penalty is 0.25 per year short,
floored at zero (PRD F4.4).
"""

from collections.abc import Sequence
from datetime import date

from src.jd import StructuredJD
from src.score.aggregate import SubScore

PENALTY_PER_YEAR = 0.25


def merge_intervals(intervals: Sequence[tuple[date, date]]) -> list[tuple[date, date]]:
    merged: list[list[date]] = []
    for start, end in sorted(intervals):
        if end < start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def years_held(intervals: Sequence[tuple[date, date]], *, today: date | None = None) -> float:
    """Distinct calendar time covered by the given intervals, in years."""
    reference = today or date.today()
    cleaned = [(start, end or reference) for start, end in intervals]
    days = sum((end - start).days for start, end in merge_intervals(cleaned))
    return round(days / 365.25, 2)


def experience_score(
    jd: StructuredJD,
    intervals: Sequence[tuple[date, date]],
    *,
    today: date | None = None,
) -> SubScore:
    held = years_held(intervals, today=today)
    required = jd.years_required

    if not required or required <= 0:
        return SubScore(
            "experience",
            1.0,
            matched=[],
            missing=[],
            detail={"held_years": held, "required_years": None, "reason": "no_requirement"},
        )

    deficit = max(0.0, required - held)
    value = 1.0 if deficit <= 0 else max(0.0, 1 - PENALTY_PER_YEAR * deficit)
    return SubScore(
        name="experience",
        value=round(value, 4),
        matched=[] if deficit > 0 else [f"{held:.2f} years"],
        # The missing term for this sub-score is literally the missing time.
        missing=[] if deficit <= 0 else [f"{deficit:.2f} years"],
        detail={
            "held_years": held,
            "required_years": required,
            "deficit_years": round(deficit, 2),
            "penalty_per_year": PENALTY_PER_YEAR,
        },
    )
