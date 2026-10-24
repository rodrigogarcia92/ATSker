"""The Keywords card, deterministic part (PRD F7.5): which missing keyword the user's own
material could back, and where it would go.

Like `score/`, this module makes no network call and imports no provider: it reads a
stored report and the user's current rows, and the same inputs always give the same card.
Nothing is stored and nothing is written — the card is computed on view, so a report
stored before F7.5 existed gets one too, from the material the user holds today.

A candidate is a keyword the Keywords sub-score lists as missing for the document (`must_have`
∪ `nice_to_have` ∪ `raw_keywords`, F5.5.2). Each is classified by the strongest evidence the
user's data holds, strongest first, and never twice:

* `pool` — its canonical is in the profile's skills pool and no bullet of the track says it;
* `bullet` — an active master bullet is tagged with the canonical (it names that bullet);
* `graded` — the grader already credits a requirement whose words are this keyword, at
  `EVIDENCE_THRESHOLD` or above and with a cited bullet (D7, "say it their way"): the
  user has the skill, the search would still miss it, and the cited bullet is where the
  posting's own word goes;
* `equivalent` — the user holds a family sibling (F5.4.1: Tableau ↔ Power BI).

A candidate with none of the four is not advised: it stays in the gap list (F6), is counted
for the card's footer, and is what the on-demand inference (`extract.generation`, F7.5's
*Probable*) is offered. Equivalence is a judgement here and nowhere in the scorer, so the
card never moves a score.
"""

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.models import Bullet, Profile, Skill, Track
from src.normalize.text import fold
from src.normalize.vocabulary import match_text
from src.score.gaps import EVIDENCE_THRESHOLD
from src.tracks import track_bullets
from src.vocabulary import alias_map

# F7.5: the first eight show; "Ver todas (N)" reveals the rest.
SHOWN = 8

BASES = ("pool", "bullet", "graded", "equivalent")
PRIORITIES = ("must_have", "nice_to_have", "other")


@dataclass(frozen=True)
class Candidate:
    """A missing keyword of the posting, with the canonical the vocabulary gives it."""

    keyword: str
    canonical: str | None
    priority: str


@dataclass(frozen=True)
class KeywordItem:
    """One advised keyword: its basis, and the place it would go."""

    keyword: str
    canonical: str | None
    priority: str
    basis: str
    # Where it goes: the skills section, or a named bullet of the master database.
    where: str
    bullet_id: str | None = None
    bullet_text: str | None = None
    # `bullet` basis: the bullet is in the track and describes the keyword without the
    # posting's word (use it), or it already says it and the track simply lacks it (add it).
    bullet_says: bool = False
    # `equivalent` basis: the family sibling the user holds.
    sibling: str | None = None


@dataclass(frozen=True)
class KeywordAdvice:
    """The card: the advised items in order, and the candidates nothing in the data backs."""

    items: list[KeywordItem] = field(default_factory=list)
    unsupported: list[Candidate] = field(default_factory=list)
    for_file: bool = False

    @property
    def shown(self) -> list[KeywordItem]:
        return self.items[:SHOWN]

    @property
    def rest(self) -> list[KeywordItem]:
        return self.items[SHOWN:]

    # D7's "Dilo con sus palabras" group: a skill the grader (or the pool, or a tagged
    # bullet) already credits but a search would miss. Equivalence is a different claim
    # and keeps its own label after the group.
    @property
    def say_it_shown(self) -> list[KeywordItem]:
        return [item for item in self.shown if item.basis != "equivalent"]

    @property
    def equivalent_shown(self) -> list[KeywordItem]:
        return [item for item in self.shown if item.basis == "equivalent"]

    @property
    def candidates(self) -> int:
        return len(self.items) + len(self.unsupported)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else []


def _canonical_of(term: str, aliases: Mapping[str, str]) -> str | None:
    return aliases.get(fold(term)) or None


def candidates_of(
    report: Mapping[str, object], aliases: Mapping[str, str]
) -> list[Candidate] | None:
    """The Keywords sub-score's missing terms, ranked must-have, nice-to-have, the rest.

    `None` for a report with no keywords sub-score (stored before w3/w4): there is nothing
    to advise and nothing to say. One entry per keyword — two spellings of one canonical
    are one candidate, the first being the name the report shows.
    """
    sub = _mapping(_mapping(_mapping(report.get("score")).get("sub_scores")).get("keywords"))
    if not sub:
        return None
    jd = _mapping(report.get("jd"))

    def key(term: str) -> str:
        folded = fold(term)
        return aliases.get(folded, folded)

    must = {key(term) for term in _strings(jd.get("must_have"))}
    nice = {key(term) for term in _strings(jd.get("nice_to_have"))}
    seen: set[str] = set()
    ranked: list[tuple[int, int, Candidate]] = []
    for index, term in enumerate(_strings(sub.get("missing"))):
        identity = key(term)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        priority = "other"
        if identity in must:
            priority = "must_have"
        elif identity in nice:
            priority = "nice_to_have"
        candidate = Candidate(term, _canonical_of(term, aliases), priority)
        ranked.append((PRIORITIES.index(priority), index, candidate))
    return [candidate for _tier, _index, candidate in sorted(ranked, key=lambda row: row[:2])]


def _skill_rows(session: Session) -> dict[str, Skill]:
    return {skill.canonical: skill for skill in session.scalars(select(Skill))}


def _siblings(canonical: str, skills: Mapping[str, Skill]) -> list[str]:
    """The other canonicals of this one's family (one hop, F5.4.1); none without a family."""
    own = skills.get(canonical)
    if own is None or not own.family:
        return []
    return sorted(
        other.canonical
        for other in skills.values()
        if other.family == own.family and other.canonical != canonical
    )


def _says(bullet: Bullet, canonical: str, aliases: Mapping[str, str], lang: str) -> bool:
    """Whether the bullet's own words name the canonical (the document is read in `lang`)."""
    return canonical in match_text(bullet_text(bullet, lang), aliases, skip_ambiguous=True)


# The words that carry no meaning of their own when a keyword meets a requirement's
# text; `c++` and `c#` survive the split, as they do in `normalize.text.match_key`.
_WORD = re.compile(r"[^a-z0-9+#]+")
_STOPWORDS = frozenset(
    {
        "a", "al", "and", "con", "de", "del", "el", "en", "for", "la", "las", "los",
        "o", "of", "on", "or", "para", "por", "the", "to", "un", "una", "with", "y",
    }
)


def _meaningful(text: str) -> list[str]:
    """The folded words of a term or a requirement that a match may rest on."""
    return [word for word in _WORD.split(fold(text)) if word and word not in _STOPWORDS]


def _graded_requirement(
    candidate: Candidate, grades: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    """The first stored grade that credits the keyword's words and cites a bullet (D7).

    A requirement at `EVIDENCE_THRESHOLD` or above is one the grader already gives the
    user credit for; its cited bullet is where the posting's own word belongs. Reading
    the stored `grades` keeps the basis identical for reports stored before `w5`.
    """
    words = set(_meaningful(candidate.keyword))
    if not words:
        return None
    for grade in grades:
        if int(grade.get("level") or 0) < EVIDENCE_THRESHOLD or not grade.get("bullet_id"):
            continue
        if words <= set(_meaningful(str(grade.get("requirement") or ""))):
            return grade
    return None


def keyword_advice(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: Mapping[str, object],
    track: Track | None = None,
    for_file: bool = False,
) -> KeywordAdvice | None:
    """F7.5's card for a stored report, from the material the user holds now.

    `report` is the analysis's — or an attempt's own, whose Keywords sub-score is the
    uploaded file's. With `for_file` the document is that file, so there is no track whose
    bullets could already say a keyword. `None` when the report predates the Keywords
    sub-score. Deterministic and read-only: no model call, nothing written.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        return None
    aliases = alias_map(session)
    candidates = candidates_of(report, aliases)
    if candidates is None:
        return None

    lang = str(_mapping(report.get("jd")).get("language") or "es")
    skills = _skill_rows(session)
    bullets = list_bullets(profile_id, session, active_only=True)
    cv = _mapping(report.get("cv"))
    if cv:
        # F11.4: the document is the CV. Its own master bullets are the ones to name
        # first (reworded ones included); only an *unchanged* one can make a keyword
        # stale, because a reworded line may be exactly where the keyword was lost.
        in_track = {str(item) for item in cv.get("represented_ids") or []}
        unchanged = {str(item) for item in cv.get("matched_ids") or []}
    else:
        in_track = (
            {str(bullet.id) for bullet in track_bullets(profile_id, session, track.id)}
            if track is not None and not for_file
            else set()
        )
        unchanged = in_track
    pool = set(profile.skills or [])
    held = pool | {skill for bullet in bullets for skill in bullet.skills}

    grades = [row for row in report.get("grades") or [] if isinstance(row, Mapping)]

    items: list[KeywordItem] = []
    unsupported: list[Candidate] = []
    for candidate in candidates:
        verdict, item = _classify(
            candidate, pool, held, bullets, in_track, unchanged, skills, aliases, lang, grades
        )
        if verdict == "item" and item is not None:
            items.append(item)
        elif verdict == "unsupported":
            unsupported.append(candidate)
    order = {basis: rank for rank, basis in enumerate(BASES)}
    items.sort(key=lambda item: (PRIORITIES.index(item.priority), order[item.basis]))
    return KeywordAdvice(items=items, unsupported=unsupported, for_file=for_file)


def _classify(
    candidate: Candidate,
    pool: set[str],
    held: set[str],
    bullets: Sequence[Bullet],
    in_track: set[str],
    unchanged: set[str],
    skills: Mapping[str, Skill],
    aliases: Mapping[str, str],
    lang: str,
    grades: Sequence[Mapping[str, object]],
) -> tuple[str, KeywordItem | None]:
    """`("item", it)` on `pool`, then `bullet`, then `graded`, then `equivalent`;
    `("unsupported", None)` when none holds; `("stale", None)` when the track's own
    bullets already say it.

    A stale keyword is no longer missing — the report is older than the material — so it is
    neither advised nor counted as unsupported.
    """
    canonical = candidate.canonical

    def item(basis: str, where: str, **extra: object) -> tuple[str, KeywordItem]:
        return "item", KeywordItem(
            candidate.keyword,
            canonical,
            candidate.priority,
            basis,
            where,
            **extra,  # type: ignore[arg-type]
        )

    if canonical is not None:
        if any(str(b.id) in unchanged and _says(b, canonical, aliases, lang) for b in bullets):
            return "stale", None
        if canonical in pool:
            return item("pool", "skills")
        tagged = [bullet for bullet in bullets if canonical in bullet.skills]
        if tagged:
            # The track's own bullet first, then the first by creation: the same one every
            # time.
            chosen = next((b for b in tagged if str(b.id) in in_track), tagged[0])
            return item(
                "bullet",
                "bullet",
                bullet_id=str(chosen.id),
                bullet_text=bullet_text(chosen, lang),
                bullet_says=_says(chosen, canonical, aliases, lang),
            )
    # D7: the grader already credits it; the bullet it cited is where to use the posting's
    # word. Works without a canonical too — the stored requirement's text is the evidence.
    graded = _graded_requirement(candidate, grades)
    if graded is not None:
        return item(
            "graded",
            "bullet",
            bullet_id=str(graded["bullet_id"]),
            bullet_text=str(graded.get("bullet_text") or "") or None,
        )
    if canonical is None:
        return "unsupported", None
    siblings = [name for name in _siblings(canonical, skills) if name in held]
    if siblings:
        return item("equivalent", "skills", sibling=siblings[0])
    return "unsupported", None
