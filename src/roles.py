"""Data access for roles. `profile_id` first, ownership inside the query.

A role's title has a language (PRD F4.2): `title_es` and `title_en` are what a
posting in that language reads, and `title` keeps the title in the role's primary
language for the code, the snapshots and the stored reports that read it. Which
language is primary is decided once, by `role_language`, with the same rules the
`0011` migration backfilled with — a second answer here would be a second
convention, and the two would drift the first time one of them changed.
"""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.models import Role, Track, TrackBullet
from src.resumes import get_resume
from src.scoping import owned_row, owned_rows


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def list_roles(profile_id: uuid.UUID, session: Session, *, active_only: bool = False) -> list[Role]:
    roles = owned_rows(Role, session, profile_id, active_only=active_only)
    return sorted(roles, key=lambda role: role.start_date or date.min, reverse=True)


def get_role(profile_id: uuid.UUID, session: Session, role_id: str | uuid.UUID) -> Role | None:
    return owned_row(Role, session, profile_id, role_id)


def role_language(
    profile_id: uuid.UUID,
    session: Session,
    role_id: uuid.UUID | str | None = None,
    *,
    language: str | None = None,
) -> str:
    """The language a role's content is in (PRD F4.2), and therefore its `title`.

    F4.2's order, the one `0011` backfilled with: the draft language of the résumé
    behind the role's earliest bullet with provenance; otherwise the language most of
    its bullets are written in, a tie falling through; otherwise the `lang` of a track
    holding one of its bullets; otherwise `es`. A role with no bullets — one being
    created by hand, or by a form that submitted both titles — has no evidence, so it
    falls through to the last rule.

    `language` short-circuits the rules with a language the caller already knows: a
    merge creating a role from a document knows the draft's, and that is rule 1 read
    from the document instead of from the bullets it is about to write.
    """
    if language in ("es", "en"):
        return language
    bullets = (
        list_bullets(profile_id, session, role_id=role_id, active_only=False)
        if role_id is not None
        else []
    )
    # `list_bullets` is ordered by creation, so the earliest evidence is read first.
    for bullet in bullets:
        if bullet.source_resume_id is None:
            continue
        resume = get_resume(profile_id, session, bullet.source_resume_id)
        named = ((resume.draft or {}) if resume is not None else {}).get("language")
        if named:
            return "en" if named == "en" else "es"

    written_es = sum(1 for bullet in bullets if _clean(bullet.text_es))
    written_en = sum(1 for bullet in bullets if _clean(bullet.text_en))
    if written_es != written_en:
        return "es" if written_es > written_en else "en"

    if bullets:
        track_lang = session.scalar(
            select(Track.lang)
            .join(TrackBullet, TrackBullet.track_id == Track.id)
            .where(
                Track.profile_id == profile_id,
                TrackBullet.bullet_id.in_([bullet.id for bullet in bullets]),
            )
            .order_by(Track.id)
            .limit(1)
        )
        if track_lang == "en":
            return "en"
    return "es"


def role_title(role: Role, lang: str | None = None) -> tuple[str, bool]:
    """The role's title as one reader sees it, and whether it fell back (PRD F4.2).

    Read exactly like a bullet's text (F4.1): the posting's language first, the other
    one second and marked as a fallback — a recruiter's screen matches the words in
    the file, so which file the title came from is worth knowing. `title` is the last
    resort for a row whose two columns are empty; it carries no language of its own,
    so it is not a fallback.
    """
    own, other = ("en", "es") if lang == "en" else ("es", "en")
    preferred = _clean(getattr(role, f"title_{own}"))
    if preferred:
        return preferred, False
    fallback = _clean(getattr(role, f"title_{other}"))
    if fallback:
        return fallback, True
    return (role.title or "").strip(), False


def mirror_title(title_es: str | None, title_en: str | None, language: str) -> str:
    """What `title` holds: the primary language's title, or the other one when it is
    the only one filled. Never a translation: an empty column stays empty."""
    own, other = ("en", "es") if language == "en" else ("es", "en")
    titles = {"es": _clean(title_es), "en": _clean(title_en)}
    return titles[own] or titles[other] or ""


def create_role(
    profile_id: uuid.UUID,
    session: Session,
    *,
    employer: str,
    title_es: str | None,
    title_en: str | None,
    start_date: date | None = None,
    end_date: date | None = None,
    language: str | None = None,
) -> Role:
    """A position held. The two titles are the input; `title` is derived, not passed.

    Taking `title` as an argument too would let a caller write a row whose three
    columns disagree, which is the one thing F4.2's split cannot survive.
    """
    role = Role(
        profile_id=profile_id,
        employer=employer.strip(),
        title=mirror_title(
            title_es, title_en, role_language(profile_id, session, language=language)
        ),
        title_es=_clean(title_es),
        title_en=_clean(title_en),
        start_date=start_date,
        end_date=end_date,
    )
    session.add(role)
    session.flush()
    return role


def update_role(
    profile_id: uuid.UUID,
    session: Session,
    role_id: str | uuid.UUID,
    *,
    employer: str,
    title_es: str | None,
    title_en: str | None,
    start_date: date | None,
    end_date: date | None,
    active: bool = True,
    language: str | None = None,
) -> Role | None:
    role = get_role(profile_id, session, role_id)
    if role is None:
        return None
    role.employer = employer.strip()
    # The primary language is read before the write, from the bullets as they are:
    # the title being saved is a title, never evidence of the role's language.
    role.title = mirror_title(
        title_es, title_en, role_language(profile_id, session, role_id, language=language)
    )
    role.title_es = _clean(title_es)
    role.title_en = _clean(title_en)
    role.start_date = start_date
    role.end_date = end_date
    role.active = active
    session.flush()
    return role


def set_role_active(
    profile_id: uuid.UUID, session: Session, role_id: str | uuid.UUID, *, active: bool
) -> Role | None:
    """Deactivate rather than delete: historical reports still need to render."""
    role = get_role(profile_id, session, role_id)
    if role is None:
        return None
    role.active = active
    session.flush()
    return role
