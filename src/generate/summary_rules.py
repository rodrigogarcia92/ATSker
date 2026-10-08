"""The three style rules of a proposed summary, checked by code (PRD F7.3, `summary_v4`).

The shortlist of key skills is built here, deterministically, from the stored report: the
model never chooses it. The checks are pure — the text, the title, the shortlist and the
vocabulary come in; a list of `{rule, ok, detail}` comes out — so they run without a
provider. `propose_summary` is the one orchestration with a provider: one call, and at most
one retry that names the failed rules. A style rule that still fails is shown, never a block.
"""

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.extract.generation import BaseLike, Proposal, generate_summary
from src.jd import StructuredJD
from src.normalize.text import fold
from src.normalize.vocabulary import match_text

TITLE_RULE = "title"
SKILLS_RULE = "skills"
LENGTH_RULE = "length"
RULES = (TITLE_RULE, SKILLS_RULE, LENGTH_RULE)

SHORTLIST_MAX = 4
SKILLS_MIN = 3
MAX_WORDS = 80

_SENTENCE_END = ".!?\n"
_SPACES = re.compile(r"\s+")

# What the model is told when a rule failed; the rule's name alone would not say enough.
_FAILED = {
    TITLE_RULE: "the first sentence must contain the posting's title exactly as given",
    SKILLS_RULE: "name three or four skills from the shortlist (all of them if fewer than "
    "three), and no skill outside it",
    LENGTH_RULE: f"the summary must have at most {MAX_WORDS} words",
}


@dataclass(frozen=True)
class KeySkill:
    """A shortlisted skill: the posting's wording and the canonical the vocabulary gives it."""

    wording: str
    canonical: str


def key_skill_shortlist(
    report: Mapping[str, Any], pool: frozenset[str], aliases: Mapping[str, str]
) -> list[KeySkill]:
    """The posting's must-haves, then nice-to-haves, graded level >= 2 on a direct basis.

    Only a canonical in the profile's pool qualifies; equivalent and transferable credit
    never does (F5.4.1). Posting order, one entry per canonical, at most four.
    """
    jd = report.get("jd") or {}
    grades: dict[str, Mapping[str, Any]] = {}
    for grade in report.get("grades") or []:
        grades.setdefault(fold(str(grade.get("requirement") or "")), grade)
    chosen: list[KeySkill] = []
    seen: set[str] = set()
    for term in [*(jd.get("must_have") or []), *(jd.get("nice_to_have") or [])]:
        wording = str(term)
        grade = grades.get(fold(wording))
        canonical = aliases.get(fold(wording))
        if (
            grade is None
            or int(grade.get("level") or 0) < 2
            or grade.get("basis") != "direct"
            or not canonical
            or canonical not in pool
            or canonical in seen
        ):
            continue
        seen.add(canonical)
        chosen.append(KeySkill(wording, canonical))
        if len(chosen) == SHORTLIST_MAX:
            break
    return chosen


def _squash(text: str) -> str:
    return _SPACES.sub(" ", text).strip().casefold()


def check_title(text: str, title: str) -> dict[str, Any]:
    """The title, verbatim, in the first sentence. Case and whitespace runs are ignored;
    accents are not."""
    squashed, wanted = _squash(text), _squash(title)
    position = squashed.find(wanted) if wanted else -1
    ok = position >= 0 and not any(mark in squashed[:position] for mark in _SENTENCE_END)
    return {"rule": TITLE_RULE, "ok": ok, "detail": title}


def check_skills(
    text: str, shortlist: Sequence[KeySkill], aliases: Mapping[str, str]
) -> dict[str, Any]:
    """The distinct skills named number 3 or 4 (the shortlist's size when it is smaller),
    and at least min(3, shortlist) of them are from the shortlist."""
    found = match_text(text, aliases, skip_ambiguous=True)
    listed = {skill.canonical for skill in shortlist}
    if len(shortlist) < SKILLS_MIN:
        count_ok = len(found) == len(shortlist)
    else:
        count_ok = SKILLS_MIN <= len(found) <= SHORTLIST_MAX
    ok = count_ok and len(listed & set(found)) >= min(SKILLS_MIN, len(shortlist))
    return {"rule": SKILLS_RULE, "ok": ok, "detail": ", ".join(found)}


def check_length(text: str) -> dict[str, Any]:
    """At most 80 words. Words, not sentences."""
    words = len(text.split())
    return {"rule": LENGTH_RULE, "ok": words <= MAX_WORDS, "detail": str(words)}


def check_style(
    text: str, *, title: str, shortlist: Sequence[KeySkill], aliases: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The three checks, in the order the pop-up lists them."""
    return [check_title(text, title), check_skills(text, shortlist, aliases), check_length(text)]


def _text_of(proposal: Proposal) -> str:
    return str(proposal.output["summary"]["text"])


def propose_summary(
    session: Session,
    *,
    jd: StructuredJD,
    bullets: Sequence[tuple[str, str]],
    track_skills: Sequence[str],
    pool: Sequence[str],
    grades: Sequence[Mapping[str, Any]],
    language: str,
    title: str,
    base: BaseLike | None,
    shortlist: Sequence[KeySkill],
    aliases: Mapping[str, str],
    banned: Sequence[str],
    call: Callable[..., Proposal] = generate_summary,
    **options: Any,
) -> tuple[Proposal, list[dict[str, Any]]]:
    """One call, and one retry if a style rule failed; the answer satisfying more rules wins.

    On a tie the second answer is kept. Never more than two calls. Both go through
    `complete_json`, so the ledger keeps both.
    """

    def run(retry: tuple[str, Sequence[str]] | None) -> tuple[Proposal, list[dict[str, Any]]]:
        proposal = call(
            session,
            jd=jd,
            bullets=bullets,
            track_skills=track_skills,
            pool=pool,
            grades=grades,
            language=language,
            title=title,
            base=base,
            shortlist=[(skill.wording, skill.canonical) for skill in shortlist],
            banned=banned,
            retry=retry,
            **options,
        )
        return proposal, check_style(
            _text_of(proposal), title=title, shortlist=shortlist, aliases=aliases
        )

    first, checklist = run(None)
    failed = [row["rule"] for row in checklist if not row["ok"]]
    if not failed:
        return first, checklist
    second, second_checklist = run((_text_of(first), [_FAILED[rule] for rule in failed]))
    if sum(row["ok"] for row in second_checklist) >= sum(row["ok"] for row in checklist):
        return second, second_checklist
    return first, checklist


__all__ = [
    "KeySkill",
    "check_length",
    "check_skills",
    "check_style",
    "check_title",
    "key_skill_shortlist",
    "propose_summary",
]
