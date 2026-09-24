"""Gap detection and disqualifier verdicts (PRD F6, F6.1): deterministic and free.

Every gap falls out of the grading already performed — a requirement graded level 0
or 1 — so the gap list and the score can never disagree, and no provider call is
made here (the boundary test walks this package and enforces it).

Detection orders the gaps in F6.1's bands: must-have at level 0, must-have at 1,
nice-to-have at 0, nice-to-have at 1 — and after them F6.1's fifth band, *covered
by transfer*, the requirements a transfer credit covers but a recruiter may still
question. Within a band the order the job description stated them in is kept —
the order `jd.must_have` / `jd.nice_to_have` already carry. Same posting, same
order, every time.

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
    basis: str = "direct"
    transfer_reason: str | None = None


@dataclass(frozen=True)
class Gap:
    """A requirement the evidence does not cover, and the bullet that came close.

    `transfer_reason` marks F6.1's fifth band: a requirement at level 2 or 3 whose
    basis is `equivalent` or `transferable`. It is not a gap in the score's sense —
    it is the claim most likely to be questioned — so it is listed with its reason
    and never counted against anything.
    """

    requirement: str
    level: int
    must_have: bool
    bullet_id: str | None = None
    bullet_text: str | None = None
    transfer_reason: str | None = None

    @property
    def covered_by_transfer(self) -> bool:
        return self.transfer_reason is not None


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
    """The four gap bands, then F6.1's fifth, in band order (PRD F6, F6.1).

    At level 1 a bullet came close: its id and its snapshotted text travel with the
    gap. At level 0 nothing supported the requirement, so there is no bullet to cite.

    The fifth band is *covered by transfer*: a requirement at level 2 or 3 whose
    basis is `equivalent` or `transferable`, carrying its `transfer_reason`. It is
    not a gap for scoring — it is listed after the four bands so the user knows
    which arguments to prepare (F6.1) — and it keeps its citation for the same
    reason: that evidence *is* the argument.
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
    covered = [
        Gap(
            requirement=entry.requirement,
            level=entry.level,
            must_have=entry.must_have,
            bullet_id=entry.bullet_id,
            bullet_text=entry.bullet_text,
            transfer_reason=entry.transfer_reason,
        )
        for entry in graded
        if entry.level >= EVIDENCE_THRESHOLD and entry.basis in ("equivalent", "transferable")
    ]

    def band(gap: Gap) -> int:
        if gap.covered_by_transfer:
            return 4
        return (0 if gap.must_have else 2) + (0 if gap.level == 0 else 1)

    def stated(gap: Gap) -> int:
        sequence = must_have if gap.must_have else nice_to_have
        try:
            return sequence.index(gap.requirement)
        except ValueError:
            return len(sequence)

    return sorted([*gaps, *covered], key=lambda gap: (band(gap), stated(gap)))


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


# The location ask, with the same deliberate conservatism: word tokens that name a
# place kind ("presencial en Lima", "onsite_lima"), never a city name. A
# requirement this cannot recognise stays out of the alert rather than in it.
_LOCATION_TOKENS = frozenset(
    {
        "presencial",
        "onsite",
        "hibrido",
        "hybrid",
        "remoto",
        "remote",
        "sede",
        "oficina",
        "office",
        "ciudad",
        "city",
        "ubicacion",
        "location",
        "reubicacion",
        "relocation",
    }
)


def location_requirements(verdicts: Sequence[Disqualifier]) -> list[Disqualifier]:
    """The hard requirements that concern location (F6.1's alert beside the warning).

    Location never enters the number (F5.5.1); it is a real screening risk, so the
    verdicts of the requirements that ask for one are reported as an alert — beside
    the single warning, never inside the gap list.
    """
    return [
        verdict
        for verdict in verdicts
        if any(token in _LOCATION_TOKENS for token in _TOKENS.split(fold(verdict.requirement)))
    ]
