"""The whole CV one reader sees (PRD F4.1), in one language at a time (F5.5.1).

`track_document` is the single source of truth for what an analysis reads: the
headline, the summary, the skills list, the bullets, the role titles, the education
and the certifications, in `lang`, falling back to the other language per item and
marking every fallback (F4.1: Spanish evidence against an English posting is weaker
to a recruiter than an English one, and the report says that it happened).

With `track is None` it reproduces the document F5.2 has always scanned: every
active bullet with an active role, the profile's headline and summary, and the
skill chips the bullets carry. The chips are not a curated skills list — decision
32's exclusion of `profiles.skills` stands — but they have been searchable since
F5.2 and dropping them would silently change existing behaviour. A track's own
`tracks.skills` replaces them: that selection is the skills section a reader sees,
and the one F5.4.1 shows the grader.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import bullet_text, list_bullets
from src.certifications import list_certifications
from src.education import list_educations
from src.models import Bullet, Profile, Skill, Summary, Track
from src.roles import list_roles, role_title
from src.score.ceiling import MasterBullet, MasterData, MasterRole
from src.summaries import get_summary
from src.tracks import list_tracks, track_bullets

UnitKind = Literal[
    "headline",
    "summary",
    "skills_list",
    "skill",
    "bullet",
    "role",
    "education",
    "certification",
]


@dataclass(frozen=True)
class DocumentUnit:
    """One piece of the document: its kind, its text, its source id where it has
    one (a bullet's or a pool row's id), and whether the text is a fallback to the
    other language (F4.1)."""

    kind: UnitKind
    text: str
    source_id: str | None = None
    fallback: bool = False


def document_bullets(
    profile_id: uuid.UUID, session: Session, track: Track | None
) -> list[Bullet]:
    """The bullets the document shows — the same evidence the grader receives.

    The track's selection in its order, or every active bullet; a bullet the user
    has deactivated, or whose role was, is not evidence even when a track still
    selects it. One rule, one place: the analysis and `track_document` must never
    disagree about what the person's career contains.
    """
    active_roles = {role.id for role in list_roles(profile_id, session, active_only=True)}
    selected = (
        list_bullets(profile_id, session, active_only=True)
        if track is None
        else track_bullets(profile_id, session, track.id)
    )
    return [bullet for bullet in selected if bullet.active and bullet.role_id in active_roles]


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def _language(lang: str) -> tuple[str, str]:
    """`(lang, other)` as the slots spell them: everything that is not `en` is `es`."""
    return ("en", "es") if lang == "en" else ("es", "en")


def track_document(
    profile_id: uuid.UUID,
    session: Session,
    track: Track | None,
    lang: str,
    *,
    bullets: Sequence[Bullet] | None = None,
    headline: str | None = None,
    summary_text: str | None = None,
    skills: Sequence[str] | None = None,
) -> list[DocumentUnit]:
    """The track as one reader sees it, in reading order, in `lang` (PRD F4.1).

    Every item falls back to the other language and says so with `fallback: True`.
    The headline's last resort is the profile's own (F4.1's table); that text
    carries no language of its own and is not marked as a fallback.

    The four keyword-only overrides exist for F10's ephemeral track (A4): an attempt
    reads the *file's* text where it differs from the master and the master's where it
    matches, so an unchanged export produces exactly the document the analysis scored.
    They are None here, which is the analysis path unchanged.
    """
    own, other = _language(lang)
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("a document needs a profile that exists")

    units: list[DocumentUnit] = []
    headline_given = headline is not None

    headline_text, headline_fallback = None, False
    if track is not None:
        headline_text = _clean(getattr(track, f"headline_{own}", None))
        if headline_text is None:
            headline_text = _clean(getattr(track, f"headline_{other}", None))
            headline_fallback = headline_text is not None
    if headline_text is None:
        headline_text = _clean(profile.headline)
    if headline_given:
        headline_text, headline_fallback = _clean(headline), False
    if headline_text:
        units.append(DocumentUnit("headline", headline_text, fallback=headline_fallback))

    summary: Summary | None = None
    summary_fallback = False
    summary_given = summary_text is not None
    if summary_given:
        summary_text = _clean(summary_text)
    elif track is not None:
        slot = getattr(track, f"summary_{own}_id", None)
        summary = get_summary(profile_id, session, slot) if slot else None
        if summary is None:
            slot = getattr(track, f"summary_{other}_id", None)
            summary = get_summary(profile_id, session, slot) if slot else None
            summary_fallback = summary is not None
        if summary is not None:
            summary_text = summary.text
    else:
        summary_text = _clean(profile.summary)
    if summary_text:
        units.append(
            DocumentUnit(
                "summary",
                summary_text,
                source_id=str(summary.id) if summary is not None else None,
                fallback=summary_fallback,
            )
        )

    bullets = list(bullets) if bullets is not None else document_bullets(profile_id, session, track)
    if track is not None:
        seen: set[str] = set()
        for canonical in skills if skills is not None else track.skills:
            name = _clean(canonical)
            if name and name not in seen:
                seen.add(name)
                units.append(DocumentUnit("skills_list", name))
    else:
        chips = sorted({skill for bullet in bullets for skill in bullet.skills})
        units.extend(DocumentUnit("skill", skill) for skill in chips)

    for bullet in bullets:
        text = bullet_text(bullet, lang)
        if not text:
            continue
        preferred = bullet.text_en if own == "en" else bullet.text_es
        units.append(
            DocumentUnit(
                "bullet",
                text,
                source_id=str(bullet.id),
                fallback=not bool(_clean(preferred)),
            )
        )

    # F4.2: a title is read in the posting's language and falls back to the other one
    # exactly as a bullet's text does, and the unit carries the fallback the way a
    # bullet's does — the recruiter search and the keyword scan run over these units,
    # and both have to see the words the user would send.
    for role in list_roles(profile_id, session, active_only=True):
        text, fallback = role_title(role, lang)
        if text:
            units.append(DocumentUnit("role", text, source_id=str(role.id), fallback=fallback))
    units.extend(
        DocumentUnit(
            "education",
            " ".join(part for part in (entry.institution, entry.degree, entry.field) if part),
        )
        for entry in list_educations(profile_id, session)
    )
    units.extend(
        DocumentUnit(
            "certification", " ".join(part for part in (entry.name, entry.issuer) if part)
        )
        for entry in list_certifications(profile_id, session)
    )
    return [unit for unit in units if unit.text]


def document_headline(document: Sequence[DocumentUnit]) -> str | None:
    """The document's headline item, for the title sub-score (F5.5)."""
    return next((unit.text for unit in document if unit.kind == "headline"), None)


def document_skills_list(document: Sequence[DocumentUnit]) -> str | None:
    """The skills section as one line — the source F5.4.1 shows the grader."""
    names = [unit.text for unit in document if unit.kind == "skills_list"]
    return ", ".join(names) if names else None


def document_summary(document: Sequence[DocumentUnit]) -> str | None:
    """The summary item — the other source F5.4.1 shows the grader."""
    return next((unit.text for unit in document if unit.kind == "summary"), None)


def master_data(
    profile_id: uuid.UUID, session: Session, track: Track | None = None
) -> MasterData:
    """Everything the ceiling may read from the master database (F10.2, A2/A10).

    Plain values, so `score.ceiling` stays a pure function: every active role with its
    titles in both languages and its bullets, every active bullet with its tags and its
    text, every stored headline, the skills pool, and the one-hop skill families. The
    track — when the analysis had one — contributes its skills to the pool.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        raise RuntimeError("master data needs a profile that exists")
    roles = list_roles(profile_id, session, active_only=True)
    bullets = document_bullets(profile_id, session, None)
    by_role: dict[uuid.UUID, list[str]] = {}
    for bullet in bullets:
        by_role.setdefault(bullet.role_id, []).append(str(bullet.id))

    headlines = [
        headline
        for entry in list_tracks(profile_id, session, active_only=True)
        for headline in (entry.headline_es, entry.headline_en)
        if headline
    ]
    if profile.headline:
        headlines.append(profile.headline)

    families = {
        skill.canonical: skill.family
        for skill in session.scalars(select(Skill))
        if skill.family
    }
    return MasterData(
        bullets=tuple(
            MasterBullet(
                id=str(bullet.id),
                role_id=str(bullet.role_id),
                text_es=bullet.text_es,
                text_en=bullet.text_en,
                skills=tuple(bullet.skills),
            )
            for bullet in bullets
        ),
        roles=tuple(
            MasterRole(
                id=str(role.id),
                title_es=role.title_es,
                title_en=role.title_en,
                start_date=role.start_date,
                end_date=role.end_date,
                bullet_ids=tuple(by_role.get(role.id, ())),
            )
            for role in roles
        ),
        headlines=tuple(headlines),
        pool=tuple([*profile.skills, *(track.skills if track is not None else [])]),
        families=families,
    )
