"""Experience (weight 0.25): the years that count, and the tasks already done.

`experience_score` is `w3`'s rule — every year held against what the posting asks
for — and it stays beside this one because a `w3` report is read from its own keys
and its own version: re-deriving its number has to use the rule that produced it.

`relevant_experience_score` is `w4`'s (F5.5.2). It narrows the years to the ones a
recruiter would count: a role is relevant when one of its bullets is cited at
level 2 or better for a requirement or a posting task, and it counts in full for
a `direct` or `equivalent` citation and half for a `transferable` one. Then it
adds the posting's own responsibilities, already done — the second thing a
recruiter checks after the years.

Concurrent roles are merged before counting (both rules), so two overlapping jobs
cannot add up to more experience than the calendar holds.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from src.jd import StructuredJD
from src.score.aggregate import SubScore
from src.score.evidence import EVIDENCE_THRESHOLD, MAX_LEVEL

PENALTY_PER_YEAR = 0.25


@dataclass(frozen=True)
class RoleSpan:
    """One role, the calendar time it covers, and the bullets that belong to it."""

    id: str
    title: str
    start_date: date | None
    end_date: date | None
    bullet_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class CitedLevel:
    """One graded item reduced to what Experience reads (F5.5.2).

    `basis` is a requirement's evidence basis; a task citation is always `direct`,
    because a described task is the thing itself rather than a transfer of it.
    """

    level: int
    basis: str
    bullet_id: str | None
    text: str = ""


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


def _spans(roles: Sequence[RoleSpan], *, today: date) -> list[tuple[date, date]]:
    """The counted calendar time of the given roles; a role with no start does not count."""
    return [
        (role.start_date, role.end_date or today) for role in roles if role.start_date is not None
    ]


def relevant_experience_score(
    required_years: float | None,
    roles: Sequence[RoleSpan],
    requirement_grades: Sequence[CitedLevel],
    task_grades: Sequence[CitedLevel],
    *,
    split: Mapping[str, float],
    today: date | None = None,
) -> SubScore:
    """PRD F5.5.2's Experience: relevant years and the posting's tasks already done.

    `requirement_grades` and `task_grades` are the judge's answers as they stand
    after the family backstop, reduced to level, basis and cited bullet. A role is
    relevant when one of its bullets is cited at level `EVIDENCE_THRESHOLD` or
    better: full weight for a `direct` or `equivalent` citation (a task citation
    is `direct`), half for `transferable` only. Overlapping relevant roles are
    merged before they are summed, so a second concurrent job cannot double the
    calendar.
    """
    reference = today or date.today()
    owner = {bullet_id: role for role in roles for bullet_id in role.bullet_ids}
    weight: dict[str, float] = {}
    cited_all = [(grade, False) for grade in requirement_grades] + [
        (grade, True) for grade in task_grades
    ]
    for cited, is_task in cited_all:
        if cited.level < EVIDENCE_THRESHOLD or not cited.bullet_id:
            continue
        role = owner.get(cited.bullet_id)
        if role is None:
            continue
        offered = 1.0 if is_task or cited.basis in ("direct", "equivalent") else 0.5
        weight[role.id] = max(weight.get(role.id, 0.0), offered)

    full = [role for role in roles if weight.get(role.id) == 1.0]
    half = [role for role in roles if weight.get(role.id) == 0.5]
    held = years_held(_spans(roles, today=reference), today=reference)
    full_years = years_held(_spans(full, today=reference), today=reference)
    union_years = years_held(_spans([*full, *half], today=reference), today=reference)
    relevant_years = round(full_years + 0.5 * (union_years - full_years), 2)

    if required_years and required_years > 0:
        deficit = max(0.0, required_years - relevant_years)
        years_part = max(0.0, 1 - PENALTY_PER_YEAR * deficit)
    else:
        deficit = 0.0
        years_part = min(1.0, relevant_years)

    task_part = (
        sum(grade.level for grade in task_grades) / (MAX_LEVEL * len(task_grades))
        if task_grades
        else 0.0
    )
    detail: dict[str, object] = {
        "held_years": held,
        "relevant_years": relevant_years,
        "required_years": required_years,
        "years_part": round(years_part, 4),
        "task_part": round(task_part, 4),
        "relevant_roles": [
            {"id": role.id, "title": role.title, "weight": weight[role.id]}
            for role in roles
            if role.id in weight
        ],
        "tasks": [
            {"text": grade.text, "level": grade.level, "bullet_id": grade.bullet_id}
            for grade in task_grades
        ],
    }
    if not task_grades:
        # F5.5.2: a posting that names no tasks cannot be scored on having done
        # them, so Experience is the years part alone and the report says why.
        detail["reason"] = "no_responsibilities"
        value = years_part
    else:
        value = split["years"] * years_part + split["tasks"] * task_part

    return SubScore(
        name="experience",
        value=round(value, 4),
        matched=[f"{relevant_years:.2f} years"] if deficit <= 0 else [],
        missing=[] if deficit <= 0 else [f"{deficit:.2f} years"],
        detail=detail,
    )
