"""The three style rules of a proposed summary, checked by code (PRD F7.3, `summary_v6`).

Two of the three things the summary needs are built here, deterministically, from the stored
report: the shortlist of key skills and the career title it opens with. The model never
chooses either. The checks are pure — the text, the title, the shortlist and the vocabulary
come in; a list of `{rule, ok, detail}` comes out — so they run without a provider.
`propose_summary` is the one orchestration with a provider: one call, and at most one retry
that names the failed rules. A style rule that still fails is shown, never a block.
"""

import re
import uuid
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from src.extract.generation import BaseLike, Proposal, generate_summary
from src.generate.validators import CLOSURE_RULES, LITERAL, Violation
from src.jd import StructuredJD
from src.models import Track
from src.normalize.text import fold, term_pattern
from src.normalize.vocabulary import ambiguous_aliases, match_text
from src.roles import list_roles, mirror_title
from src.score.title import FUNCTION_WORDS, title_tokens

TITLE_RULE = "title"
SKILLS_RULE = "skills"
LENGTH_RULE = "length"
RULES = (TITLE_RULE, SKILLS_RULE, LENGTH_RULE)

SHORTLIST_MAX = 4
SKILLS_MIN = 3
MIN_WORDS = 60
MAX_WORDS = 100

_SENTENCE_END = ".!?\n"
_SPACES = re.compile(r"\s+")

# What the model is told when a rule failed; the rule's name alone would not say enough.
_FAILED = {
    TITLE_RULE: "the first sentence must open with the career title exactly as written",
    SKILLS_RULE: "name three or four skills from the shortlist (all of them if fewer than "
    "three), and no skill outside it",
    LENGTH_RULE: f"the summary must be between {MIN_WORDS} and {MAX_WORDS} words",
}


STEP_POSTING = "posting"
STEP_RELATED = "related"


@dataclass(frozen=True)
class KeySkill:
    """A shortlisted skill: the wording to use and the canonical the vocabulary gives it.

    `step` says where it came from: the posting's own requirement (`posting`, F7.3 rule 2) or a
    skill the user shows in a bullet that carries a requirement (`related`, the fallback ladder).
    """

    wording: str
    canonical: str
    step: str = STEP_POSTING


def _in_order_of_appearance(text: str, aliases: Mapping[str, str]) -> list[str]:
    """The pool-agnostic canonicals matched in `text`, by where they first appear."""
    found = match_text(text, aliases, skip_ambiguous=True)
    haystack = fold(text)
    ambiguous = ambiguous_aliases()
    position: dict[str, int] = {}
    for alias, canonical in aliases.items():
        if canonical not in found or alias in ambiguous:
            continue
        hit = term_pattern(alias).search(haystack)
        if hit is not None:
            position[canonical] = min(hit.start(), position.get(canonical, hit.start()))
    return sorted(found, key=lambda canonical: position.get(canonical, len(haystack)))


def key_skill_shortlist(
    report: Mapping[str, Any],
    pool: frozenset[str],
    aliases: Mapping[str, str],
    *,
    bullet_texts: Mapping[str, str] | None = None,
) -> list[KeySkill]:
    """Up to four key skills, in three steps that each add only canonicals not yet chosen.

    (a) The posting's must-haves, then nice-to-haves, graded level >= 2 on a direct basis and
    in the pool, in the posting's order and wording. Equivalent and transferable credit never
    qualifies (F5.4.1).
    (b) The user's own skills that carry the requirements: for each grade at level >= 2,
    must-haves first, the pool canonicals matched in that grade's bullet, in the order they
    appear there, in the vocabulary's canonical wording.
    (c) Other pool canonicals in any bullet graded >= 2 for this posting, the most evidenced
    first, then alphabetically.

    Every skill returned is one the closure validator accepts for a summary that cites the
    bullet showing it.
    """
    texts = bullet_texts or {}
    jd = report.get("jd") or {}
    grade_list = [grade for grade in report.get("grades") or [] if isinstance(grade, Mapping)]
    grades: dict[str, Mapping[str, Any]] = {}
    for grade in grade_list:
        grades.setdefault(fold(str(grade.get("requirement") or "")), grade)
    chosen: list[KeySkill] = []
    seen: set[str] = set()

    def full() -> bool:
        return len(chosen) >= SHORTLIST_MAX

    def add(wording: str, canonical: str, step: str) -> None:
        if not full() and canonical not in seen and canonical in pool:
            seen.add(canonical)
            chosen.append(KeySkill(wording, canonical, step))

    for term in [*(jd.get("must_have") or []), *(jd.get("nice_to_have") or [])]:
        wording = str(term)
        grade = grades.get(fold(wording))
        canonical = aliases.get(fold(wording))
        if (
            grade is not None
            and int(grade.get("level") or 0) >= 2
            and grade.get("basis") == "direct"
            and canonical
        ):
            add(wording, canonical, STEP_POSTING)

    evidenced = [
        grade
        for grade in grade_list
        if int(grade.get("level") or 0) >= 2 and str(grade.get("bullet_id") or "") in texts
    ]
    for must in (True, False):
        for grade in evidenced:
            if bool(grade.get("must_have")) != must:
                continue
            for canonical in _in_order_of_appearance(texts[str(grade["bullet_id"])], aliases):
                add(canonical, canonical, STEP_RELATED)

    shown: Counter[str] = Counter()
    for bullet_id in {str(grade["bullet_id"]) for grade in evidenced}:
        shown.update(
            canonical
            for canonical in match_text(texts[bullet_id], aliases, skip_ambiguous=True)
            if canonical in pool
        )
    for canonical in sorted(shown, key=lambda name: (-shown[name], name)):
        add(canonical, canonical, STEP_RELATED)
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
    """Between 60 and 100 words. Words, not sentences."""
    words = len(text.split())
    return {
        "rule": LENGTH_RULE,
        "ok": MIN_WORDS <= words <= MAX_WORDS,
        "detail": str(words),
    }


def check_style(
    text: str, *, title: str, shortlist: Sequence[KeySkill], aliases: Mapping[str, str]
) -> list[dict[str, Any]]:
    """The three checks. The retry and the stored checklist read all three; the pop-up
    hides the length row, so no word limit is ever shown to the user."""
    return [check_title(text, title), check_skills(text, shortlist, aliases), check_length(text)]


def career_title(
    profile_id: uuid.UUID,
    session: Session,
    track: Track,
    title: str,
    aliases: Mapping[str, str],
    language: str,
) -> str:
    """The title the summary opens with, chosen by code — never by the model (F7.3).

    The posting's own title only when one title the person holds carries **every** content
    token of it: a role title or the track's headline, compared as the Title sub-score
    compares (folded, alias-expanded tokens with the function words of both languages
    removed). Otherwise the track's headline in the posting's language — the user's own
    catch-all title for this career — and otherwise the most recent held role title in that
    language. A profile that holds no title at all keeps the posting's, so there is always
    one to open with.
    """

    def content(text: str) -> set[str]:
        return {token for token in title_tokens(text, aliases) if token not in FUNCTION_WORDS}

    wanted = content(title)
    roles = list_roles(profile_id, session)
    held = [track.headline_es, track.headline_en]
    for role in roles:
        held.extend((role.title, role.title_es, role.title_en))
    if wanted and any(wanted <= content(text) for text in held if text):
        return title
    headline = (track.headline_es if language == "es" else track.headline_en) or ""
    if headline.strip():
        return headline.strip()
    for role in roles:
        named = mirror_title(role.title_es, role.title_en, language)
        if named.strip():
            return named.strip()
    return title


def _text_of(proposal: Proposal) -> str:
    return str(proposal.output["summary"]["text"])


def violation_instruction(violation: Violation) -> str:
    """What the retry tells the model about one validator finding, built from the finding."""
    if violation.rule in CLOSURE_RULES:
        return f"remove «{violation.text}»: no cited bullet shows it"
    if violation.rule == LITERAL:
        return f"remove «{violation.text}»: it is not in the sources you cite"
    return "cite only ids that were given"


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
    validate: Callable[[Mapping[str, Any]], list[Violation]],
    call: Callable[..., Proposal] = generate_summary,
    **options: Any,
) -> tuple[Proposal, list[dict[str, Any]], list[Violation]]:
    """One call, and one retry if a style rule or a validator failed.

    `validate` runs the three validators over a proposal's output (the caller closes over
    its sources). The retry names the failed style rules and, per finding, the word to remove
    or the citation to fix. The answer with no validator finding wins; if both or neither have
    one, the answer passing more style rules; on a tie, the second. Never more than two calls;
    both go through `complete_json`, so the ledger keeps both. Returns the chosen answer, its
    checklist and its findings.
    """

    def run(
        retry: tuple[str, Sequence[str]] | None,
    ) -> tuple[Proposal, list[dict[str, Any]], list[Violation]]:
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
            shortlist=[(skill.wording, skill.canonical, skill.step) for skill in shortlist],
            banned=banned,
            retry=retry,
            **options,
        )
        checklist = check_style(
            _text_of(proposal), title=title, shortlist=shortlist, aliases=aliases
        )
        return proposal, checklist, validate(proposal.output)

    first, checklist, violations = run(None)
    failed = [row["rule"] for row in checklist if not row["ok"]]
    if not failed and not violations:
        return first, checklist, violations
    instructions = [_FAILED[rule] for rule in failed]
    for violation in violations:
        instruction = violation_instruction(violation)
        if instruction not in instructions:
            instructions.append(instruction)
    second, second_checklist, second_violations = run((_text_of(first), instructions))
    if bool(violations) != bool(second_violations):
        return (second, second_checklist, second_violations) if not second_violations else (
            first,
            checklist,
            violations,
        )
    if sum(row["ok"] for row in second_checklist) >= sum(row["ok"] for row in checklist):
        return second, second_checklist, second_violations
    return first, checklist, violations


__all__ = [
    "KeySkill",
    "career_title",
    "check_length",
    "check_skills",
    "check_style",
    "check_title",
    "key_skill_shortlist",
    "propose_summary",
    "violation_instruction",
]
