"""Edit advice (PRD F7.2, *The rules, exactly*): deterministic rules over the report.

Rule 3 and the skill branch of rule 4 were retired on 2026-10-05: the Keywords card
(`src.keyword_advice`, F7.5) says which skill to surface, and on which basis.

No provider call, ever: every line here is arithmetic on the report the analysis just
produced plus the user's own rows, so the same report always yields the same advice
and a stored report re-renders without a model. The sentences are built per language
when the page renders (`src.web.alerts.advice_line`); what is stored is the kind, the
ids and the snapshot the line cites.

Design principle 6 is the closure check: an item whose canonical is not evidenced in
the user's own data is dropped, never reworded — the gap list (F6) is where an
unevidenced requirement belongs. Rules 1 to 4 are about the selected track and advise
nothing without one; the title and language rules are about the document.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.models import Bullet, Profile, Track
from src.normalize.text import fold
from src.roles import list_roles
from src.score.title import FUNCTION_WORDS, title_tokens
from src.tracks import track_bullets
from src.vocabulary import alias_map

# PRD F7.2: "At most eight items, in that order."
MAX_ITEMS = 8

# The level that means "this requirement is demonstrated" (F5.5.2), and the level
# below which a must-have is worth trying to raise with a line the user already has.
DEMONSTRATED = 3
WORTH_RAISING = 2

# Rule 1 speaks of the first three positions of the track.
PROMOTE_INTO = 3

# A title sub-score below this is a mismatch worth an edit, not a rounding error.
TITLE_FLOOR = 0.5


@dataclass(frozen=True)
class AdviceItem:
    """One line of advice: what to change, where, and the stored evidence.

    `values` are the numbers and names the sentence needs, in their stored form: a
    language is an ISO code the page translates, never the render's own language.
    """

    kind: str
    evidence: str = ""
    bullet_id: str | None = None
    role_id: str | None = None
    canonical: str | None = None
    query_label: str | None = None
    values: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _snapshot(grade: Mapping[str, object], bullet: Bullet | None) -> str:
    """The citation's snapshot when the report has one, else the row as it stands."""
    text = _clean(str(grade.get("bullet_text") or ""))
    if text:
        return text
    return bullet_text(bullet) if bullet is not None else ""


def _canonical(term: str | None, aliases: Mapping[str, str]) -> str | None:
    return aliases.get(fold(term or "")) or None


def _level(grade: Mapping[str, object]) -> int:
    try:
        return int(str(grade.get("level") or 0))
    except ValueError:
        return 0


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _title_score(report: Mapping[str, object]) -> float | None:
    title = _mapping(_mapping(report.get("score")).get("sub_scores")).get("title")
    value = _mapping(title).get("value")
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:  # pragma: no cover - a stored report writes a number
        return None


def _language_alert(report: Mapping[str, object]) -> Mapping[str, object] | None:
    alerts = _mapping(report.get("gaps")).get("alerts")
    for alert in alerts or []:
        if isinstance(alert, Mapping) and alert.get("kind") == "language_mismatch":
            return alert
    return None


def _queries(report: Mapping[str, object]) -> Sequence[Mapping[str, object]]:
    queries = _mapping(report.get("recall")).get("queries")
    return [query for query in queries or [] if isinstance(query, Mapping)]


def edit_advice(
    profile_id: uuid.UUID,
    session: Session,
    *,
    report: Mapping[str, object],
    track: Track | None,
) -> list[AdviceItem]:
    """F7.2's rules, in order, at most eight items (rule 3 is the Keywords card's now).

    `report` is the analysis as it will be stored — or a stored one — so this reads
    the same things the page will: the grades, the title sub-score, the recall queries
    and the F4.2 alert. Everything else comes from the rows.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        return []
    aliases = alias_map(session)
    bullets = [bullet for bullet in list_bullets(profile_id, session, active_only=True)]
    roles = list_roles(profile_id, session, active_only=True)
    selection = track_bullets(profile_id, session, track.id) if track is not None else []
    positions = {str(bullet.id): index for index, bullet in enumerate(selection)}
    by_id: dict[str, Bullet] = {str(bullet.id): bullet for bullet in bullets}
    for bullet in selection:
        by_id.setdefault(str(bullet.id), bullet)
    # The user's own data in F7.2's sense: what their lines are tagged with. The pool
    # is annotation and cannot lift a number (decision 32), so a canonical it names
    # with no bullet behind it is not evidence, and an item that leans on it is
    # dropped by the closure check below.
    evidenced = {skill for bullet in bullets for skill in bullet.skills}

    items: list[AdviceItem] = []
    seen_bullets: set[str] = set()
    seen_canonicals: set[str] = set()

    if track is not None:
        grades = [grade for grade in report.get("grades") or [] if isinstance(grade, Mapping)]
        cited = {str(grade.get("bullet_id")) for grade in grades if grade.get("bullet_id")}

        # Rule 1 — promote a bullet: demonstrated for a must-have, below the first
        # three positions, while something above it demonstrates nothing.
        for grade in grades:
            if not grade.get("must_have") or _level(grade) != DEMONSTRATED:
                continue
            bullet_id = str(grade.get("bullet_id") or "")
            position = positions.get(bullet_id)
            if position is None or position < PROMOTE_INTO or bullet_id in seen_bullets:
                continue
            above = [str(bullet.id) for bullet in selection[:position]]
            if not any(above_id not in cited for above_id in above):
                continue
            seen_bullets.add(bullet_id)
            items.append(
                AdviceItem(
                    kind="promote_bullet",
                    bullet_id=bullet_id,
                    evidence=_snapshot(grade, by_id.get(bullet_id)),
                    values={
                        "position": position + 1,
                        "requirement": _clean(str(grade.get("requirement") or "")),
                    },
                )
            )

        # Rule 2 — add a bullet to this track: a line of the master database, outside
        # the track, tagged with the canonical of a must-have graded below 2.
        wanted = sorted(
            {
                canonical
                for canonical in (
                    _canonical(str(grade.get("requirement") or ""), aliases)
                    for grade in grades
                    if grade.get("must_have") and _level(grade) < WORTH_RAISING
                )
                if canonical is not None
            }
        )
        for canonical in wanted:
            for bullet in bullets:
                bullet_id = str(bullet.id)
                if bullet_id in positions or bullet_id in seen_bullets:
                    continue
                if canonical not in bullet.skills:
                    continue
                seen_bullets.add(bullet_id)
                seen_canonicals.add(canonical)
                items.append(
                    AdviceItem(
                        kind="add_bullet",
                        bullet_id=bullet_id,
                        canonical=canonical,
                        evidence=bullet_text(bullet),
                        values={"canonical": canonical},
                    )
                )
                break

        # Rule 3 — surface a skill — is the Keywords card's now (F7.5, `keyword_advice`), which
        # also covers related and probable keywords. A report stored before it keeps its
        # `surface_skill` items and renders them as before; a new one emits none.

        # Rule 4 — a recruiter's query that fails on a term the user can evidence.
        for query in _queries(report):
            if query.get("passed"):
                continue
            for clause in query.get("clauses") or []:
                if not isinstance(clause, Mapping) or clause.get("matched"):
                    continue
                term = _clean(str(clause.get("term") or ""))
                canonical = _canonical(term, aliases)
                if canonical is None or canonical in seen_canonicals:
                    continue
                outside = [
                    bullet
                    for bullet in bullets
                    if canonical in bullet.skills and str(bullet.id) not in positions
                ]
                if outside:
                    bullet = outside[0]
                    seen_bullets.add(str(bullet.id))
                    seen_canonicals.add(canonical)
                    items.append(
                        AdviceItem(
                            kind="fix_query",
                            bullet_id=str(bullet.id),
                            canonical=canonical,
                            query_label=_clean(str(query.get("label") or "")),
                            evidence=bullet_text(bullet),
                            values={
                                "query": _clean(str(query.get("query_text") or term)),
                                "canonical": canonical,
                            },
                        )
                    )
                # No bullet says it: the keyword is the Keywords card's, or a gap (F6).

    # Rule 5 — title: under the floor with the posting's words in a title the user
    # already has in the other language (F4.2) is a translation to fill; otherwise the
    # edit is a headline.
    score = _title_score(report)
    jd_title = _clean(str(_mapping(report.get("jd")).get("title") or ""))
    if score is not None and score < TITLE_FLOOR and jd_title:
        posting = _clean(str(_mapping(report.get("jd")).get("language") or "es")) or "es"
        other = "en" if posting == "es" else "es"
        wanted_tokens = title_tokens(jd_title, aliases) - FUNCTION_WORDS
        # The rule asks for a translation that is *missing*, and for that one only: a
        # role that already carries a title in the posting's language has nothing to
        # fill, and a role the other slot translates only half of is a headline the
        # user still has to write. Every content word of the posting title, in a slot
        # that is empty — otherwise the item below is the headline.
        translated = next(
            (
                (role, text)
                for role in roles
                for text in [_clean(getattr(role, f"title_{other}", None))]
                if text
                and wanted_tokens
                and wanted_tokens <= title_tokens(text, aliases)
                and not _clean(getattr(role, f"title_{posting}", None))
            ),
            None,
        )
        if translated is not None:
            role, text = translated
            items.append(
                AdviceItem(
                    kind="title_language",
                    role_id=str(role.id),
                    evidence=text,
                    values={"title": jd_title, "role": text, "language": other},
                )
            )
        else:
            items.append(AdviceItem(kind="title_headline", values={}))

    # Rule 6 — the F4.2 alert, said as an edit.
    alert = _language_alert(report)
    if alert is not None:
        items.append(
            AdviceItem(
                kind="language",
                values={
                    "bullets": alert.get("fallback_bullets") or 0,
                    "total_bullets": alert.get("bullets") or 0,
                    "titles": alert.get("fallback_titles") or 0,
                    "language": _clean(str(alert.get("posting") or "es")) or "es",
                },
            )
        )

    kept: list[AdviceItem] = []
    for item in items:
        if item.canonical is not None and item.canonical not in evidenced:
            continue  # F7.2's closure check: dropped, never reworded
        kept.append(item)
        if len(kept) == MAX_ITEMS:
            break
    return kept
