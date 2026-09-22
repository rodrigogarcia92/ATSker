"""Gap detection and disqualifier verdicts (PRD F6, F6.1): deterministic and free.

Every gap falls out of the grading already performed — a requirement graded level 0
or 1 — so the gap list and the score can never disagree, and no provider call is
made here (the boundary test walks this package and enforces it).

Detection orders the gaps in F6.1's bands: must-have at level 0, must-have at 1,
nice-to-have at 0, nice-to-have at 1. Within a band the order the job description
stated them in is kept — the order `jd.must_have` / `jd.nice_to_have` already carry.
Same posting, same order, every time.

A disqualifier verdict answers only what the stored data decides. `unverified` is
the honest default and is never rendered as `met` (F6.1): inventing a verdict here
is the same failure as inventing a metric in a bullet.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from src.normalize.text import fold

# A level below this is a gap: the same threshold `score.evidence` scores against.
EVIDENCE_THRESHOLD = 2

Verdict = Literal["met", "unmet", "unverified"]

# Tokens that make a hard requirement an education ask — the one category a non-empty
# `educations` table can answer. Deliberately conservative: `master` is absent
# because folding makes "máster" and "master data" indistinguishable, and a false
# `unmet` would be an invented verdict. Anything unrecognised stays `unverified`.
_EDUCATION_TOKENS = frozenset(
    {
        "titulo",
        "titulacion",
        "universitario",
        "universidad",
        "licenciatura",
        "educacion",
        "formacion",
        "estudios",
        "degree",
        "bachelor",
        "bachelors",
        "university",
        "college",
        "education",
        "schooling",
    }
)

_TOKENS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class Graded:
    """One graded requirement as detection sees it — no `extract/` import (PRD 5.1)."""

    requirement: str
    level: int
    must_have: bool
    bullet_id: str | None = None
    bullet_text: str | None = None


@dataclass(frozen=True)
class Gap:
    """A requirement the evidence does not cover, and the bullet that came close."""

    requirement: str
    level: int
    must_have: bool
    bullet_id: str | None = None
    bullet_text: str | None = None


@dataclass(frozen=True)
class Disqualifier:
    requirement: str
    verdict: Verdict


def detect_gaps(
    graded: Sequence[Graded],
    *,
    must_have: Sequence[str],
    nice_to_have: Sequence[str],
) -> list[Gap]:
    """Level 0 and level 1 requirements, in F6.1's band order (PRD F6).

    At level 1 a bullet came close: its id and its snapshotted text travel with the
    gap. At level 0 nothing supported the requirement, so there is no bullet to cite.
    """
    gaps = [
        Gap(
            requirement=entry.requirement,
            level=entry.level,
            must_have=entry.must_have,
            bullet_id=entry.bullet_id if entry.level == 1 else None,
            bullet_text=entry.bullet_text if entry.level == 1 else None,
        )
        for entry in graded
        if entry.level < EVIDENCE_THRESHOLD
    ]

    def band(gap: Gap) -> int:
        return (0 if gap.must_have else 2) + (0 if gap.level == 0 else 1)

    def stated(gap: Gap) -> int:
        sequence = must_have if gap.must_have else nice_to_have
        try:
            return sequence.index(gap.requirement)
        except ValueError:
            return len(sequence)

    return sorted(gaps, key=lambda gap: (band(gap), stated(gap)))


def disqualifier_verdicts(
    hard_requirements: Sequence[str], *, has_education: bool
) -> list[Disqualifier]:
    """Three-way verdicts per hard requirement (F6.1), beside the score.

    Only an education ask is checkable against what ATSker stores: `educations`
    either holds a row or it does not. Work authorisation, an on-site city and a
    licence have no field behind them and stay `unverified` — the panel asks the
    user to confirm those rather than guessing.
    """
    verdicts: list[Disqualifier] = []
    for requirement in hard_requirements:
        if _asks_for_education(requirement):
            verdicts.append(Disqualifier(requirement, "met" if has_education else "unmet"))
        else:
            verdicts.append(Disqualifier(requirement, "unverified"))
    return verdicts


def _asks_for_education(requirement: str) -> bool:
    return any(token in _EDUCATION_TOKENS for token in _TOKENS.split(fold(requirement)))
