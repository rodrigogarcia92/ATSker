"""Assembly for generated text (PRD F7.3): what a proposal may claim, and accepting it.

Every function takes `profile_id` first and builds its `Sources` from that profile's
own rows, so a citation outside them is somebody else's row and fails provenance
without a second lookup. On accept the output is validated **again** against the
database's sources: the proposal travelled in a form, and a form is user input.

The writes go through the existing data paths — a summary joins the pool, a bullet
change keeps its old text as a revision (F2.5), a story bullet stores
`source_story_id` — so nothing accepted here bypasses a rule the rest of the app
already enforces.
"""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from src.bullets import bullet_text, create_bullet, get_bullet, list_bullets, update_bullet
from src.generate.validators import Sources, Violation, validate
from src.models import Application, Bullet, BulletRevision, Profile, Story, Summary, Track
from src.roles import get_role, list_roles
from src.stories import get_story
from src.summaries import create_summary
from src.tracks import set_track_skills, set_track_summary, track_bullets
from src.vocabulary import alias_map


def _profile(profile_id: uuid.UUID, session: Session) -> Profile | None:
    # A profile's own id is its key, so the owner-scoped lookup is the row itself.
    return session.get(Profile, profile_id)


def pool_skills(profile_id: uuid.UUID, session: Session) -> frozenset[str]:
    """Every canonical this profile may be credited with: the pool and its bullet tags.

    This is F7.3's rule 3's allowed set. The pool alone is not enough — a skill can
    be tagged on a bullet before the user adds it to their list — and a bullet tag
    alone is not either, because the pool is what the user curated.
    """
    profile = _profile(profile_id, session)
    pool: set[str] = set(profile.skills or []) if profile is not None else set()
    for bullet in list_bullets(profile_id, session, active_only=False):
        pool.update(bullet.skills or [])
    return frozenset(pool)


def report_language(application: Application) -> str:
    """The posting's language, which is the language generated output follows (PRD 8)."""
    report = application.report or {}
    return str((report.get("jd") or {}).get("language") or "es")


def grades_of(application: Application) -> list[dict[str, Any]]:
    """The stored grades, in the shape the validator reads (level, cited bullet id)."""
    report = application.report or {}
    return [
        {"level": grade.get("level", 0), "evidence_id": grade.get("bullet_id")}
        for grade in report.get("grades") or []
    ]


def summary_sources(
    profile_id: uuid.UUID, session: Session, track: Track, language: str
) -> Sources:
    """The track's bullets, in the posting's language, and the profile's skills.

    The summary may name a title the user holds (F7.3), so the track's headlines in both
    languages and every stored role title travel as `titles`: they support proper nouns.
    """
    bullets = track_bullets(profile_id, session, track.id)
    texts = {str(bullet.id): bullet_text(bullet, language) for bullet in bullets}
    titles = [track.headline_es, track.headline_en]
    for role in list_roles(profile_id, session):
        titles.extend((role.title, role.title_es, role.title_en))
    return Sources(
        bullets=texts,
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
        titles=tuple(title for title in titles if title),
    )


def bullet_sources(profile_id: uuid.UUID, session: Session, bullet: Bullet) -> Sources:
    """One bullet's both language columns — a translation keeps every number and name."""
    text = " ".join(part for part in (bullet.text_es, bullet.text_en) if part)
    return Sources(
        bullets={str(bullet.id): text},
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )


def story_sources(
    profile_id: uuid.UUID, session: Session, story: Story, roles: Sequence[Any]
) -> Sources:
    """The story's own body and the roles a derived bullet may cite."""
    titles = {}
    for role in roles:
        titles[str(role.id)] = " ".join(part for part in (role.title_es, role.title_en) if part)
    return Sources(
        stories={str(story.id): story.body},
        roles=titles,
        skills=pool_skills(profile_id, session),
        aliases=alias_map(session),
    )


def check_summary(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    track: Track,
    output: Mapping[str, Any],
) -> list[Violation]:
    """The three validators over a Tier-1 proposal, against this application's grades."""
    language = report_language(application)
    return validate(
        output,
        sources=summary_sources(profile_id, session, track, language),
        profile_id=profile_id,
        session=session,
        kind="summary",
        grades=grades_of(application),
    )


def accept_summary(
    profile_id: uuid.UUID,
    session: Session,
    application: Application,
    track: Track,
    *,
    text: str,
    cites: Sequence[str],
    skills: Sequence[str],
    use_in_track: bool,
) -> tuple[Summary | None, list[Violation]]:
    """Accept a summary: validate again, then write the pool row and the track's slots.

    The form's text is never trusted. The summary joins the pool in the posting's
    language; the skills replace the track's list (only pool canonicals can appear,
    by closure); and with "usar en este puesto" the new pool row becomes the track's
    summary for that language.
    """
    output = {"summary": {"text": text, "cites": list(cites)}, "skills": list(skills)}
    violations = check_summary(profile_id, session, application, track, output)
    if violations:
        return None, violations
    language = report_language(application)
    summary = create_summary(profile_id, session, text=text, lang=language)
    set_track_skills(profile_id, session, track.id, list(skills))
    if use_in_track:
        set_track_summary(profile_id, session, track.id, lang=language, summary_id=summary.id)
    session.flush()
    return summary, []


def check_bullet(
    profile_id: uuid.UUID,
    session: Session,
    bullet: Bullet,
    output: Mapping[str, Any],
) -> list[Violation]:
    return validate(
        output,
        sources=bullet_sources(profile_id, session, bullet),
        profile_id=profile_id,
        session=session,
        kind="bullet",
    )


def accept_bullet(
    profile_id: uuid.UUID,
    session: Session,
    bullet_id: str | uuid.UUID,
    *,
    text: str,
    cites: Sequence[str],
    language: str,
) -> tuple[Bullet | None, list[Violation]]:
    """Accept a rephrased bullet: validate again, then revise the one language column.

    The old text is kept as a revision (F2.5), so nothing is overwritten without one;
    the other language column is untouched.
    """
    bullet = get_bullet(profile_id, session, bullet_id)
    if bullet is None:
        return None, []
    output = {"text": text, "cites": list(cites)}
    violations = check_bullet(profile_id, session, bullet, output)
    if violations:
        return None, violations

    text_en, text_es = bullet.text_en, bullet.text_es
    if language == "en":
        text_en = text.strip()
    else:
        text_es = text.strip()
    session.add(
        # No résumé produced this change, so `resume_id` is NULL — the revision is
        # still append-only history, which is what F2.5 asks for.
        BulletRevision(bullet_id=bullet.id, text_en=bullet.text_en, text_es=bullet.text_es)
    )
    update_bullet(
        profile_id,
        session,
        bullet.id,
        text_en=text_en,
        text_es=text_es,
        chips=bullet.skills,
        active=bullet.active,
    )
    session.flush()
    return bullet, []


def check_story_bullet(
    profile_id: uuid.UUID,
    session: Session,
    story: Story,
    roles: Sequence[Any],
    output: Mapping[str, Any],
) -> list[Violation]:
    return validate(
        output,
        sources=story_sources(profile_id, session, story, roles),
        profile_id=profile_id,
        session=session,
        kind="story_bullets",
    )


def accept_story_bullet(
    profile_id: uuid.UUID,
    session: Session,
    *,
    story_id: str | uuid.UUID,
    role_id: str | uuid.UUID,
    text: str,
    language: str,
    chips: Sequence[str] = (),
) -> tuple[Bullet | None, list[Violation]]:
    """Accept one story-derived bullet: validate again, then create it on the role.

    The bullet stores `source_story_id`, so its provenance is permanent (PRD 3), and
    it joins no track: the user adds it to one deliberately.
    """
    story = get_story(profile_id, session, story_id)
    role = get_role(profile_id, session, role_id)
    if story is None or role is None:
        return None, []
    output = {"bullets": [{"text": text, "story_id": str(story.id), "role_id": str(role.id)}]}
    violations = check_story_bullet(profile_id, session, story, [role], output)
    if violations:
        return None, violations
    bullet = create_bullet(
        profile_id,
        session,
        role_id=role.id,
        text_en=text.strip() if language == "en" else None,
        text_es=text.strip() if language != "en" else None,
        chips=chips,
    )
    bullet.source_story_id = story.id
    session.flush()
    return bullet, []


__all__ = [
    "accept_bullet",
    "accept_story_bullet",
    "accept_summary",
    "bullet_sources",
    "check_bullet",
    "check_story_bullet",
    "check_summary",
    "grades_of",
    "pool_skills",
    "report_language",
    "story_sources",
    "summary_sources",
]
