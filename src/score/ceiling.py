"""The ceiling (PRD F10.2, A1/A2/A3/A10): what the user's own material allows.

A pure function over a stored report and the master data it may read — no session, no
network, no model. `documents.master_data` loads the master into plain values; this
module turns them into the per-sub-score ceilings, the single low/high number (A1: the
high end waits for F7.4, so `high == low`), the unreachable list, and the fingerprint
that says whether a stored ceiling is still current (A10).

The four ceilings:

* **Keywords** — the same BM25, with every posting keyword the user holds (its canonical
  in the pool or in any bullet) added to the document once. A term the user does not
  hold is not added and cannot raise the score.
* **Title** — the best `w4` overlap over every held role title, in both languages, and
  every stored headline restricted to words also held as a role title (A2's
  headline-copy exclusion).
* **Skills** — each requirement below level 2 lifted to level 2 when a master bullet is
  tagged with its canonical (`direct`) or a family sibling (`equivalent`); otherwise
  kept. An estimate.
* **Experience** — the same rule over *every* role, including the ones outside the
  track's selection, so an off-track role with a tagged bullet counts. An estimate.

The total is `Σ wᵢ · ceilingᵢ` at the report's weights, with the readability cap ignored
(F10.2): layout is fixable, so the cap does not bound the material. Every value depends
only on the inputs, so two calls on the same report return byte-identical output.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from src.jd import StructuredJD
from src.normalize.text import fold
from src.normalize.vocabulary import match_text
from src.score.evidence import MAX_LEVEL, Level, evidence_coverage
from src.score.experience import CitedLevel, RoleSpan, relevant_experience_score
from src.score.keywords import keyword_context
from src.score.title import FUNCTION_WORDS, title_tokens
from src.score.weights import W1, W2, W3, W4, WeightSet

EXACT = "exact"
ESTIMATE = "estimate"

# The weights a stored report was scored under (F10.2 "at the report's weights").
# A version this code does not know cannot be re-derived, so the current one is used
# and the report's own `weights_version` is what the caller compares.
_WEIGHTS: Mapping[str, WeightSet] = {"w1": W1, "w2": W2, "w3": W3, "w4": W4}


@dataclass(frozen=True)
class MasterBullet:
    """One master bullet as the ceiling reads it: its tags and its text."""

    id: str
    role_id: str
    text_es: str | None
    text_en: str | None
    skills: tuple[str, ...]


@dataclass(frozen=True)
class MasterRole:
    """One held role: its titles in both languages and the bullets it owns."""

    id: str
    title_es: str | None
    title_en: str | None
    start_date: date | None
    end_date: date | None
    bullet_ids: tuple[str, ...]


@dataclass(frozen=True)
class MasterData:
    """Everything the ceiling may read from the master database (F10.2).

    Plain values, not ORM rows, so the module stays pure and a test can build one by
    hand. `headlines` are every stored headline; `pool` is the user's skills pool
    (plus the track's selection when the analysis had one); `families` maps a canonical
    to its one-hop equivalence group (F5.4.1).
    """

    bullets: tuple[MasterBullet, ...]
    roles: tuple[MasterRole, ...]
    headlines: tuple[str, ...]
    pool: tuple[str, ...]
    families: Mapping[str, str]


def _version(weights: WeightSet | None, report: Mapping[str, object]) -> WeightSet:
    if weights is not None:
        return weights
    score = report.get("score") or {}
    version = str(score.get("weights_version") or "")  # type: ignore[union-attr]
    return _WEIGHTS.get(version, W4)


def _canonical(term: str, aliases: Mapping[str, str]) -> str:
    return aliases.get(fold(term), fold(term))


def _posting_terms(jd: StructuredJD, aliases: Mapping[str, str]) -> list[tuple[str, str]]:
    """`(label, key)` for every term the posting asks for, as the keyword scan does."""
    seen: set[str] = set()
    terms: list[tuple[str, str]] = []
    for value in [*jd.must_have, *jd.nice_to_have, *jd.raw_keywords]:
        cleaned = fold(value)
        if not cleaned:
            continue
        key = aliases.get(cleaned, cleaned)
        if key in seen:
            continue
        seen.add(key)
        terms.append((value, key))
    return terms


def _held_canonicals(master: MasterData, aliases: Mapping[str, str]) -> set[str]:
    """Every canonical the user's data holds: the pool, bullet tags, and bullet text.

    F10.2's Keywords ceiling reads "skills pool or any bullet", and a bullet can name
    a skill in its words without a chip on it, so both are read.
    """
    held: set[str] = set(master.pool)
    for bullet in master.bullets:
        held.update(bullet.skills)
        for text in (bullet.text_es, bullet.text_en):
            if text:
                held.update(match_text(text, aliases))
    return held


def _family_siblings(master: MasterData) -> dict[str, set[str]]:
    """canonical → the other canonicals in its family (one hop, F5.4.1)."""
    groups: dict[str, set[str]] = {}
    for canonical, family in master.families.items():
        if family:
            groups.setdefault(family, set()).add(canonical)
    siblings: dict[str, set[str]] = {}
    for members in groups.values():
        for canonical in members:
            siblings[canonical] = members - {canonical}
    return siblings


def _keyword_ceiling(
    jd: StructuredJD,
    document_texts: Sequence[str],
    master: MasterData,
    aliases: Mapping[str, str],
    current: float,
    matched: Sequence[str],
) -> float:
    held = _held_canonicals(master, aliases)
    extra = [
        label
        for label, key in _posting_terms(jd, aliases)
        if key in held and label not in matched
    ]
    value = keyword_context(jd, [*document_texts, *extra], aliases=aliases).value
    return max(current, value)


def _title_ceiling(
    jd: StructuredJD,
    master: MasterData,
    aliases: Mapping[str, str],
    current: float,
) -> float:
    wanted = title_tokens(jd.title, aliases) - FUNCTION_WORDS
    if not wanted:
        return current

    held_title_tokens: set[str] = set()
    best = 0.0
    for role in master.roles:
        available = set()
        for title in (role.title_es, role.title_en):
            if title:
                available |= title_tokens(title, aliases)
        available -= FUNCTION_WORDS
        held_title_tokens |= available
        best = max(best, len(wanted & available) / len(wanted))

    # A2: a stored headline counts only through words that some held role title also
    # has — a headline cannot add a word the user never held as a title.
    for headline in master.headlines:
        if not headline:
            continue
        available = (title_tokens(headline, aliases) - FUNCTION_WORDS) & held_title_tokens
        best = max(best, len(wanted & available) / len(wanted))

    return max(current, round(best, 4))


def _skills_ceiling(
    grades: Sequence[Mapping[str, object]],
    master: MasterData,
    aliases: Mapping[str, str],
    siblings: Mapping[str, set[str]],
    basis_credit: Mapping[str, float],
    skills_weight: float,
    current: float,
) -> tuple[float, list[dict[str, object]]]:
    tagged: set[str] = {skill for bullet in master.bullets for skill in bullet.skills}
    lifted: list[Level] = []
    unreachable: list[dict[str, object]] = []
    total_weight = 0.0
    weights_by_requirement: list[tuple[Level, float]] = []
    for grade in grades:
        requirement = str(grade.get("requirement") or "")
        level = int(grade.get("level") or 0)
        must_have = bool(grade.get("must_have"))
        basis = str(grade.get("basis") or "direct")
        canonical = _canonical_from_text(requirement, aliases)
        weight = 0.75 if must_have else 0.25
        total_weight += weight
        if level < 2:
            if canonical in tagged:
                level, basis = 2, "direct"
            elif siblings.get(canonical, set()) & tagged:
                level, basis = 2, "equivalent"
            if level < 2:
                weights_by_requirement.append((Level(requirement, level, must_have, basis), weight))
        lifted.append(Level(requirement, level, must_have, basis))
    value = evidence_coverage(lifted, basis_credit=basis_credit).value
    # The points each unreachable requirement holds out of 100 of the *total* (A2): its
    # share of the Skills weight, at the level it stays on, with direct credit assumed
    # for the two levels it cannot reach, scaled by Skills' weight in the total.
    for entry, weight in weights_by_requirement:
        if total_weight <= 0:
            continue
        share = weight / total_weight
        held = (
            share
            * ((2 - entry.level) / MAX_LEVEL)
            * basis_credit.get("direct", 1.0)
            * skills_weight
        )
        unreachable.append({"requirement": entry.requirement, "points": round(held * 100, 2)})
    return max(current, value), unreachable


def _canonical_from_text(requirement: str, aliases: Mapping[str, str]) -> str:
    found = match_text(requirement, aliases, limit=1)
    return found[0] if found else _canonical(requirement, aliases)


def _experience_ceiling(
    jd: StructuredJD,
    report: Mapping[str, object],
    master: MasterData,
    aliases: Mapping[str, str],
    siblings: Mapping[str, set[str]],
    split: Mapping[str, float],
    current: float,
    today: date | None,
) -> float:
    grades = [grade for grade in (report.get("grades") or []) if isinstance(grade, Mapping)]
    requirement_grades = [
        CitedLevel(
            level=int(grade.get("level") or 0),
            basis=str(grade.get("basis") or "direct"),
            bullet_id=str(grade["bullet_id"]) if grade.get("bullet_id") else None,
            text=str(grade.get("requirement") or ""),
        )
        for grade in grades
    ]
    tasks = _task_grades(report)
    # The ceiling rule (F10.2): a role outside the track counts when one of its bullets
    # is tagged with a requirement's canonical (direct) or a family sibling
    # (equivalent). Every master bullet is offered that way; on-track bullets that were
    # already graded simply keep their citation.
    direct: set[str] = set()
    equivalent: set[str] = set()
    for grade in grades:
        canonical = _canonical_from_text(str(grade.get("requirement") or ""), aliases)
        direct.add(canonical)
        equivalent |= siblings.get(canonical, set())
    synthetic: list[CitedLevel] = []
    for bullet in master.bullets:
        tags = set(bullet.skills)
        if tags & direct:
            synthetic.append(CitedLevel(level=2, basis="direct", bullet_id=bullet.id))
        elif tags & equivalent:
            synthetic.append(CitedLevel(level=2, basis="equivalent", bullet_id=bullet.id))
    roles = [
        RoleSpan(
            id=role.id,
            title=role.title_es or role.title_en or "",
            start_date=role.start_date,
            end_date=role.end_date,
            bullet_ids=role.bullet_ids,
        )
        for role in master.roles
    ]
    value = relevant_experience_score(
        jd.years_required,
        roles,
        [*requirement_grades, *synthetic],
        tasks,
        split=split,
        today=today,
    ).value
    return max(current, value)


def _task_grades(report: Mapping[str, object]) -> list[CitedLevel]:
    """The posting's tasks as the stored Experience detail kept them."""
    score = report.get("score") or {}
    sub_scores = score.get("sub_scores") or {}  # type: ignore[union-attr]
    detail = (sub_scores.get("experience") or {}).get("detail") or {}  # type: ignore[union-attr]
    return [
        CitedLevel(
            level=int(row.get("level") or 0),
            basis="direct",
            bullet_id=str(row["bullet_id"]) if row.get("bullet_id") else None,
            text=str(row.get("text") or ""),
        )
        for row in detail.get("tasks") or []  # type: ignore[union-attr]
        if isinstance(row, Mapping)
    ]


def _fingerprint(master: MasterData, track_bullet_ids: Sequence[str]) -> str:
    """Deterministic hash of the inputs the ceiling read (A10)."""
    payload = {
        "bullets": sorted((bullet.id, sorted(bullet.skills)) for bullet in master.bullets),
        "roles": sorted(
            (role.id, role.title_es or "", role.title_en or "", sorted(role.bullet_ids))
            for role in master.roles
        ),
        "headlines": sorted(headline for headline in master.headlines if headline),
        "pool": sorted(master.pool),
        "track_bullets": sorted(track_bullet_ids),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_ceiling(
    jd: StructuredJD,
    *,
    report: Mapping[str, object],
    document_texts: Sequence[str],
    master: MasterData,
    aliases: Mapping[str, str],
    track_bullet_ids: Sequence[str] = (),
    weights: WeightSet | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """The ceiling for one stored report, from the current master data (F10.2/A1).

    Deterministic and offline: the same report and master produce the same dict, byte
    for byte, and no provider fixture is touched. `weights` overrides the report's own
    version for tests; the report's `weights_version` selects the set otherwise.
    """
    chosen = _version(weights, report)
    score = report.get("score") or {}
    sub_scores = score.get("sub_scores") or {}  # type: ignore[union-attr]

    def current(name: str) -> float:
        return float((sub_scores.get(name) or {}).get("value") or 0.0)  # type: ignore[union-attr]

    keyword_detail = sub_scores.get("keywords") or {}  # type: ignore[union-attr]
    matched = tuple(keyword_detail.get("matched") or [])  # type: ignore[union-attr]

    siblings = _family_siblings(master)
    basis_credit = getattr(chosen, "basis_credit", W4.basis_credit)
    experience_split = getattr(chosen, "experience_split", W4.experience_split)

    keyword_value = _keyword_ceiling(
        jd, document_texts, master, aliases, current("keywords"), matched
    )
    title_value = _title_ceiling(jd, master, aliases, current("title"))
    skills_value, unreachable = _skills_ceiling(
        [grade for grade in (report.get("grades") or []) if isinstance(grade, Mapping)],
        master,
        aliases,
        siblings,
        basis_credit,
        float(getattr(chosen, "skills", W4.skills)),
        current("skills"),
    )
    experience_value = _experience_ceiling(
        jd,
        report,
        master,
        aliases,
        siblings,
        experience_split,
        current("experience"),
        today,
    )

    ceilings = {
        "skills": skills_value,
        "experience": experience_value,
        "title": title_value,
        "keywords": keyword_value,
    }
    weighted = sum(getattr(chosen, name) * value for name, value in ceilings.items())
    total = round(100 * min(1.0, max(0.0, weighted)))

    return {
        "sub_scores": {
            name: {
                "current": round(current(name), 4),
                "ceiling": round(value, 4),
                "confidence": EXACT if name in ("keywords", "title") else ESTIMATE,
            }
            for name, value in ceilings.items()
        },
        "low": total,
        "high": total,
        "high_basis": "pending_f7_4",
        "unreachable": {
            "points": round(100 - total),
            "requirements": sorted(
                unreachable, key=lambda row: (-float(row["points"]), str(row["requirement"]))
            ),
        },
        "fingerprint": _fingerprint(master, track_bullet_ids),
        "weights_version": chosen.version,
    }
