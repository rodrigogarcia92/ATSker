"""Permanent deletion (PRD F2.8): one function per row of the §F2.8 table.

**Eliminar** is permanent; **Ocultar** (the `active` flags) stays what it was. Every
function here takes `profile_id` first and filters ownership inside its own query
(`src.scoping`), so another profile's row is simply "not found". Every function is
one unit of work: it flushes and the route commits, which makes `delete_everything`'s
composition one transaction.

Dependent rows are deleted or cleared here explicitly instead of left to the
database's `ON DELETE` actions: the numbers the confirmation screen showed must be
the numbers that go, and the offline tests create the schema in SQLite where foreign
keys are not enforced.

What every row's delete keeps is §F2.8's table itself: bullets survive their CV
unless "only this CV contributed" is ticked (and never when their provenance is
unknown), stories survive their role with the link cleared, reports survive their
bullet because they already snapshot the text they cite (F5.4), and the shared
vocabulary survives every user.

The ledger holds personal data (F2.8): `delete_everything` blanks `response_json`
and marks the row `degenerate` for the profile's personal-content purposes, keeping
tokens and cost. JD extraction and boolean-query derivation are not personal and
stay whole. Rows with no `profile_id` cannot be attributed to anyone; the
confirmation screen says so and `llm_costs.py purge --hash` stays the tool for them.

Deleting the login account itself is not part of F2.8.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from src.extract.gaps import PURPOSE as GAP_INTERPRET
from src.extract.generation import (
    GENERATE_BULLET,
    GENERATE_SUMMARY,
    KEYWORD_INFER,
    LETTER_BLOCKS,
    LETTER_BRIDGE,
    STORY_BULLETS,
)
from src.extract.grading import PURPOSE as EVIDENCE_GRADE
from src.extract.resume import PURPOSE as RESUME_EXTRACT
from src.extract.stories import PURPOSE as STORY_SUGGEST
from src.models import (
    Application,
    ApplicationAttempt,
    Bullet,
    BulletRevision,
    LetterSettings,
    LetterTemplate,
    LlmCall,
    Profile,
    Resume,
    Role,
    Story,
    StoryBullet,
    Summary,
    Track,
    TrackBullet,
)
from src.normalize.text import fold
from src.scoping import owned_row, owned_rows

# F2.8's personal-content purposes, as the ledger records them. `jd_extract` and
# `boolean_queries` are deliberately absent: those answers are not personal and are
# kept whole. F7.3's three added theirs, and F8's two letter calls: generated prose is
# the user's own material, so "Eliminar todo" blanks it like the résumé it came from.
# F10's attempt calls (A9): the file a user tests is theirs, so "Eliminar todo" blanks
# these answers like the résumé extraction they mirror. F7.5's `keyword_infer` joins them:
# its answer quotes the user's own bullets. The pipeline that writes them
# arrives in Run B; the names are ledger strings, so the redaction is correct the day
# the first call is made.
ATTEMPT_EXTRACT = "attempt_extract"
ATTEMPT_GRADE = "attempt_grade"

PERSONAL_PURPOSES = (
    RESUME_EXTRACT,
    EVIDENCE_GRADE,
    GAP_INTERPRET,
    STORY_SUGGEST,
    GENERATE_SUMMARY,
    GENERATE_BULLET,
    STORY_BULLETS,
    LETTER_BLOCKS,
    LETTER_BRIDGE,
    KEYWORD_INFER,
    ATTEMPT_EXTRACT,
    ATTEMPT_GRADE,
)

# What `delete_everything` totals: one key per entity of the §F2.8 table, plus the
# ledger rows it redacted. Link and revision counts stay out — the per-row functions
# report them, and summing those across a composition would double-count.
EVERYTHING_KEYS = (
    "resumes",
    "roles",
    "bullets",
    "summaries",
    "tracks",
    "stories",
    "letter_templates",
    "letter_settings",
    "applications",
    "application_attempts",
    "skills",
    "ledger_redacted",
)


def _count(session: Session, stmt) -> int:
    return int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def _bullet_ids(profile_id: uuid.UUID, session: Session, *criteria) -> list[uuid.UUID]:
    stmt = select(Bullet.id).where(Bullet.profile_id == profile_id, *criteria)
    return list(session.scalars(stmt))


def _delete_bullets(
    profile_id: uuid.UUID, session: Session, bullet_ids: Sequence[uuid.UUID]
) -> dict[str, int]:
    """Delete bullets with the three things that hang off them (§F2.8's Bullet row).

    Their place in every track, their story links and their revisions go with them;
    the reports that cited them keep their snapshotted copy and are never touched.
    """
    ids = list(bullet_ids)
    counts = {"bullets": 0, "tracks": 0, "story_links": 0, "revisions": 0}
    if not ids:
        return counts
    counts["bullets"] = len(ids)
    counts["tracks"] = int(
        session.scalar(
            select(func.count(func.distinct(TrackBullet.track_id))).where(
                TrackBullet.bullet_id.in_(ids)
            )
        )
        or 0
    )
    counts["story_links"] = _count(
        session, select(StoryBullet.bullet_id).where(StoryBullet.bullet_id.in_(ids))
    )
    counts["revisions"] = _count(
        session, select(BulletRevision.id).where(BulletRevision.bullet_id.in_(ids))
    )
    session.execute(delete(TrackBullet).where(TrackBullet.bullet_id.in_(ids)))
    session.execute(delete(StoryBullet).where(StoryBullet.bullet_id.in_(ids)))
    session.execute(delete(BulletRevision).where(BulletRevision.bullet_id.in_(ids)))
    session.execute(delete(Bullet).where(Bullet.id.in_(ids), Bullet.profile_id == profile_id))
    session.flush()
    return counts


def _cited_bullet_ids(report: dict | None) -> set[str]:
    """Every bullet id a stored report cites, wherever the report keeps one."""
    found: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "bullet_id" and value:
                    found.add(str(value))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(report or {})
    return found


# --- CV (résumé) -------------------------------------------------------------


def delete_resume(
    profile_id: uuid.UUID,
    session: Session,
    resume_id: str | uuid.UUID,
    *,
    delete_bullets: bool = False,
) -> dict[str, int] | None:
    """§F2.8's CV row: the archived file and its draft.

    The bullets it contributed are kept unless `delete_bullets` — the "delete the
    bullets only this CV contributed" tick — and even then only the ones whose
    provenance is this CV: a bullet no CV is known for is never deleted by it.
    Everything that merely points at the document (revisions, summaries, surviving
    bullets) keeps its row and loses the pointer.
    """
    resume = owned_row(Resume, session, profile_id, resume_id)
    if resume is None:
        return None
    counts = {"resumes": 1, "bullets": 0}
    if delete_bullets:
        contributed = _bullet_ids(profile_id, session, Bullet.source_resume_id == resume.id)
        counts["bullets"] = _delete_bullets(profile_id, session, contributed)["bullets"]
    session.execute(
        update(BulletRevision)
        .where(BulletRevision.resume_id == resume.id)
        .values(resume_id=None)
    )
    # F11.10: the analyses of this CV keep their report, which names the file; SQLite does
    # not enforce `ON DELETE SET NULL`, so the pointer is cleared here.
    session.execute(
        update(Application)
        .where(Application.profile_id == profile_id, Application.resume_id == resume.id)
        .values(resume_id=None)
    )
    session.execute(
        update(Summary).where(Summary.source_resume_id == resume.id).values(source_resume_id=None)
    )
    session.execute(
        update(Bullet)
        .where(Bullet.profile_id == profile_id, Bullet.source_resume_id == resume.id)
        .values(source_resume_id=None)
    )
    session.delete(resume)
    session.flush()
    return counts


def impact_resume(
    profile_id: uuid.UUID, session: Session, resume_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers: the CV goes; `bullets` is what the tick would also delete."""
    resume = owned_row(Resume, session, profile_id, resume_id)
    if resume is None:
        return None
    return {
        "resumes": 1,
        # F11.10: the analyses made on this CV, which keep their report and its file name.
        "analyses": _count(
            session,
            select(Application.id).where(
                Application.profile_id == profile_id, Application.resume_id == resume.id
            ),
        ),
        "bullets": _count(
            session,
            select(Bullet.id).where(
                Bullet.profile_id == profile_id, Bullet.source_resume_id == resume.id
            ),
        ),
        "bullets_unknown": _count(
            session,
            select(Bullet.id).where(
                Bullet.profile_id == profile_id, Bullet.source_resume_id.is_(None)
            ),
        ),
    }


# --- Role --------------------------------------------------------------------


def delete_role(
    profile_id: uuid.UUID, session: Session, role_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Role row: the role, its bullets and their revisions.

    Stories linked to it survive with the link cleared — the row says so.
    """
    role = owned_row(Role, session, profile_id, role_id)
    if role is None:
        return None
    removed = _delete_bullets(
        profile_id, session, _bullet_ids(profile_id, session, Bullet.role_id == role.id)
    )
    session.execute(update(Story).where(Story.role_id == role.id).values(role_id=None))
    session.delete(role)
    session.flush()
    return {"roles": 1, "bullets": removed["bullets"], "revisions": removed["revisions"]}


def impact_role(
    profile_id: uuid.UUID, session: Session, role_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers: bullets and revisions go; `stories` survive with a cleared link."""
    role = owned_row(Role, session, profile_id, role_id)
    if role is None:
        return None
    bullet_ids = _bullet_ids(profile_id, session, Bullet.role_id == role.id)
    return {
        "roles": 1,
        "bullets": len(bullet_ids),
        "revisions": _count(
            session, select(BulletRevision.id).where(BulletRevision.bullet_id.in_(bullet_ids))
        )
        if bullet_ids
        else 0,
        "stories": _count(
            session,
            select(Story.id).where(Story.profile_id == profile_id, Story.role_id == role.id),
        ),
    }


# --- Bullet ------------------------------------------------------------------


def delete_bullet(
    profile_id: uuid.UUID, session: Session, bullet_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Bullet row: its place in every track, its story links, its revisions.

    Reports that cited it keep their snapshotted copy (F5.4) and are not touched.
    """
    bullet = owned_row(Bullet, session, profile_id, bullet_id)
    if bullet is None:
        return None
    return _delete_bullets(profile_id, session, [bullet.id])


def impact_bullet(
    profile_id: uuid.UUID, session: Session, bullet_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers ("in 3 tracks and cited by 5 analyses; the analyses keep their
    copy"): `analyses` survives with its snapshot and is counted to say so."""
    bullet = owned_row(Bullet, session, profile_id, bullet_id)
    if bullet is None:
        return None
    counts = _delete_numbers(profile_id, session, bullet.id)
    counts["analyses"] = sum(
        1
        for application in owned_rows(Application, session, profile_id)
        if str(bullet.id) in _cited_bullet_ids(application.report)
    )
    return counts


def _delete_numbers(
    profile_id: uuid.UUID, session: Session, bullet_id: uuid.UUID
) -> dict[str, int]:
    """What `_delete_bullets` would remove for this bullet, without removing it."""
    return {
        "bullets": 1,
        "tracks": int(
            session.scalar(
                select(func.count(func.distinct(TrackBullet.track_id))).where(
                    TrackBullet.bullet_id == bullet_id
                )
            )
            or 0
        ),
        "story_links": _count(
            session, select(StoryBullet.bullet_id).where(StoryBullet.bullet_id == bullet_id)
        ),
        "revisions": _count(
            session, select(BulletRevision.id).where(BulletRevision.bullet_id == bullet_id)
        ),
    }


# --- Skill -------------------------------------------------------------------


def delete_skill(profile_id: uuid.UUID, session: Session, skill: str) -> dict[str, int] | None:
    """§F2.8's Skill row: the profile's pool entry and its place in every track.

    The shared vocabulary row survives — no user can delete it — so this is a list
    edit on the profile and its tracks, matched folded like everything else that
    reads skill names.
    """
    wanted = fold(skill)
    profile = session.get(Profile, profile_id)
    if profile is None:
        return None
    pool = [value for value in profile.skills if fold(value) != wanted]
    pool_removed = len(profile.skills) - len(pool)
    tracks_removed = 0
    for track in owned_rows(Track, session, profile_id):
        kept = [value for value in track.skills if fold(value) != wanted]
        if len(kept) != len(track.skills):
            track.skills = kept
            tracks_removed += 1
    if not pool_removed and not tracks_removed:
        return None
    profile.skills = pool
    session.flush()
    return {"pool": pool_removed, "tracks": tracks_removed}


def impact_skill(profile_id: uuid.UUID, session: Session, skill: str) -> dict[str, int] | None:
    """Screen numbers: the pool entry and the tracks that stop listing the skill."""
    wanted = fold(skill)
    profile = session.get(Profile, profile_id)
    if profile is None:
        return None
    pool_removed = sum(1 for value in profile.skills if fold(value) == wanted)
    tracks_removed = sum(
        1
        for track in owned_rows(Track, session, profile_id)
        if any(fold(value) == wanted for value in track.skills)
    )
    if not pool_removed and not tracks_removed:
        return None
    return {"pool": pool_removed, "tracks": tracks_removed}


# --- Summary -----------------------------------------------------------------


def delete_summary(
    profile_id: uuid.UUID, session: Session, summary_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Summary row: the pool row; the tracks using it lose that slot."""
    summary = owned_row(Summary, session, profile_id, summary_id)
    if summary is None:
        return None
    touched = 0
    for track in owned_rows(Track, session, profile_id):
        if summary.id not in (track.summary_es_id, track.summary_en_id):
            continue
        if track.summary_es_id == summary.id:
            track.summary_es_id = None
        if track.summary_en_id == summary.id:
            track.summary_en_id = None
        touched += 1
    session.delete(summary)
    session.flush()
    return {"summaries": 1, "tracks": touched}


def impact_summary(
    profile_id: uuid.UUID, session: Session, summary_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers: the pool row goes; `tracks` lose the slot but keep existing."""
    summary = owned_row(Summary, session, profile_id, summary_id)
    if summary is None:
        return None
    return {
        "summaries": 1,
        "tracks": sum(
            1
            for track in owned_rows(Track, session, profile_id)
            if summary.id in (track.summary_es_id, track.summary_en_id)
        ),
    }


# --- Track -------------------------------------------------------------------


def delete_track(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Track row: the track and its selection.

    Bullets stay; analyses keep the snapshotted track name in their report and only
    lose the pointer.
    """
    track = owned_row(Track, session, profile_id, track_id)
    if track is None:
        return None
    selection = _count(
        session, select(TrackBullet.bullet_id).where(TrackBullet.track_id == track.id)
    )
    session.execute(delete(TrackBullet).where(TrackBullet.track_id == track.id))
    session.execute(
        update(Application).where(Application.track_id == track.id).values(track_id=None)
    )
    session.execute(update(Resume).where(Resume.track_id == track.id).values(track_id=None))
    session.delete(track)
    session.flush()
    return {"tracks": 1, "selection": selection}


def impact_track(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers: the track and its selection go; `analyses` keep their snapshot."""
    track = owned_row(Track, session, profile_id, track_id)
    if track is None:
        return None
    return {
        "tracks": 1,
        "selection": _count(
            session, select(TrackBullet.bullet_id).where(TrackBullet.track_id == track.id)
        ),
        "analyses": _count(
            session,
            select(Application.id).where(
                Application.profile_id == profile_id, Application.track_id == track.id
            ),
        ),
    }


# --- Story and letter template ------------------------------------------------


def delete_story(
    profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Story row: the row and its links. The bullets it linked stay."""
    story = owned_row(Story, session, profile_id, story_id)
    if story is None:
        return None
    links = _count(session, select(StoryBullet.bullet_id).where(StoryBullet.story_id == story.id))
    session.execute(delete(StoryBullet).where(StoryBullet.story_id == story.id))
    session.execute(
        update(Bullet)
        .where(Bullet.profile_id == profile_id, Bullet.source_story_id == story.id)
        .values(source_story_id=None)
    )
    session.delete(story)
    session.flush()
    return {"stories": 1, "links": links}


def impact_story(
    profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID
) -> dict[str, int] | None:
    """Screen numbers: the story and its bullet links go; the bullets stay."""
    story = owned_row(Story, session, profile_id, story_id)
    if story is None:
        return None
    return {
        "stories": 1,
        "links": _count(
            session, select(StoryBullet.bullet_id).where(StoryBullet.story_id == story.id)
        ),
    }


def delete_letter_template(
    profile_id: uuid.UUID, session: Session, letter_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's letter-template half: the row and its links.

    Applications that used it keep their letter: `letter_template_id` is nulled (the
    FK is SET NULL too, but doing it here keeps one session's flush consistent) and
    `letter_text` is a snapshot, so what was sent is unchanged.
    """
    letter = owned_row(LetterTemplate, session, profile_id, letter_id)
    if letter is None:
        return None
    session.execute(
        update(Application)
        .where(
            Application.profile_id == profile_id,
            Application.letter_template_id == letter.id,
        )
        .values(letter_template_id=None)
    )
    session.delete(letter)
    session.flush()
    return {"letter_templates": 1}


def impact_letter_template(
    profile_id: uuid.UUID, session: Session, letter_id: str | uuid.UUID
) -> dict[str, int] | None:
    letter = owned_row(LetterTemplate, session, profile_id, letter_id)
    if letter is None:
        return None
    return {"letter_templates": 1}


# --- Analysis ----------------------------------------------------------------


def delete_application(
    profile_id: uuid.UUID, session: Session, application_id: str | uuid.UUID
) -> dict[str, int] | None:
    """§F2.8's Analysis row: the stored application and its attempts (F10). Golden-set
    files live outside the database and are nobody's to delete here."""
    application = owned_row(Application, session, profile_id, application_id)
    if application is None:
        return None
    attempts = list(
        session.scalars(
            select(ApplicationAttempt).where(
                ApplicationAttempt.application_id == application.id
            )
        )
    )
    if attempts:
        # F11.10: a CV saved from one of these attempts keeps living; it only forgets which.
        session.execute(
            update(Resume)
            .where(
                Resume.profile_id == profile_id,
                Resume.source_attempt_id.in_([attempt.id for attempt in attempts]),
            )
            .values(source_attempt_id=None)
        )
    for attempt in attempts:
        session.delete(attempt)
    session.delete(application)
    session.flush()
    return {"applications": 1, "application_attempts": len(attempts)}


def impact_application(
    profile_id: uuid.UUID, session: Session, application_id: str | uuid.UUID
) -> dict[str, int] | None:
    application = owned_row(Application, session, profile_id, application_id)
    if application is None:
        return None
    return {
        "applications": 1,
        "application_attempts": _count(
            session,
            select(ApplicationAttempt.id).where(
                ApplicationAttempt.application_id == application.id
            ),
        ),
    }


# --- Everything --------------------------------------------------------------


def delete_everything(profile_id: uuid.UUID, session: Session) -> dict[str, int]:
    """§F2.8's Everything row: the whole table for this profile, plus the ledger.

    Composed from the per-row functions in dependency order — bullets before the
    roles that own them, applications before the evidence they cite — so every row
    goes through the same code the single deletes use. Then the personal-content
    ledger rows of this profile are blanked and marked `degenerate`, keeping tokens
    and cost; `jd_extract` and `boolean_queries` rows are kept whole.

    What stays is the row's own Keeps column: the login, and the profile row,
    blanked (headline, summary, skills, standing risks).
    """
    totals = dict.fromkeys(EVERYTHING_KEYS, 0)
    for application in owned_rows(Application, session, profile_id):
        removed = delete_application(profile_id, session, application.id)
        if removed:
            totals["applications"] += 1
            totals["application_attempts"] += removed["application_attempts"]
    totals["bullets"] = _delete_bullets(
        profile_id, session, _bullet_ids(profile_id, session)
    )["bullets"]
    for role in owned_rows(Role, session, profile_id):
        if delete_role(profile_id, session, role.id):
            totals["roles"] += 1
    for resume in owned_rows(Resume, session, profile_id):
        if delete_resume(profile_id, session, resume.id):
            totals["resumes"] += 1
    for summary in owned_rows(Summary, session, profile_id):
        if delete_summary(profile_id, session, summary.id):
            totals["summaries"] += 1
    for track in owned_rows(Track, session, profile_id):
        if delete_track(profile_id, session, track.id):
            totals["tracks"] += 1
    for story in owned_rows(Story, session, profile_id):
        if delete_story(profile_id, session, story.id):
            totals["stories"] += 1
    for letter in owned_rows(LetterTemplate, session, profile_id):
        if delete_letter_template(profile_id, session, letter.id):
            totals["letter_templates"] += 1
    for settings in owned_rows(LetterSettings, session, profile_id):
        session.delete(settings)
        totals["letter_settings"] += 1
    profile = session.get(Profile, profile_id)
    if profile is not None:
        for skill in list(profile.skills):
            if delete_skill(profile_id, session, skill):
                totals["skills"] += 1

    totals["ledger_redacted"] = int(
        session.execute(
            update(LlmCall)
            .where(LlmCall.profile_id == profile_id, LlmCall.purpose.in_(PERSONAL_PURPOSES))
            .values(response_json={}, degenerate=True)
        ).rowcount
        or 0
    )
    if profile is not None:
        profile.headline = None
        profile.summary = None
        profile.skills = []
        profile.standing_risks = []
    session.flush()
    return totals


def impact_everything(profile_id: uuid.UUID, session: Session) -> dict[str, int]:
    """Screen numbers for Eliminar todo.

    `ledger_unattributable` is global on purpose: rows written before
    `llm_calls.profile_id` existed belong to nobody's count, and the screen says so
    rather than pretending they go with this deletion.
    """
    profile = session.get(Profile, profile_id)
    totals = {
        "resumes": _count(session, select(Resume.id).where(Resume.profile_id == profile_id)),
        "roles": _count(session, select(Role.id).where(Role.profile_id == profile_id)),
        "bullets": _count(session, select(Bullet.id).where(Bullet.profile_id == profile_id)),
        "summaries": _count(session, select(Summary.id).where(Summary.profile_id == profile_id)),
        "tracks": _count(session, select(Track.id).where(Track.profile_id == profile_id)),
        "stories": _count(session, select(Story.id).where(Story.profile_id == profile_id)),
        "letter_templates": _count(
            session, select(LetterTemplate.id).where(LetterTemplate.profile_id == profile_id)
        ),
        "letter_settings": _count(
            session, select(LetterSettings.id).where(LetterSettings.profile_id == profile_id)
        ),
        "applications": _count(
            session, select(Application.id).where(Application.profile_id == profile_id)
        ),
        "application_attempts": _count(
            session,
            select(ApplicationAttempt.id).where(
                ApplicationAttempt.profile_id == profile_id
            ),
        ),
        "skills": len(profile.skills) if profile is not None else 0,
        "ledger_redacted": _count(
            session,
            select(LlmCall.id).where(
                LlmCall.profile_id == profile_id, LlmCall.purpose.in_(PERSONAL_PURPOSES)
            ),
        ),
        "ledger_unattributable": _count(
            session,
            select(LlmCall.id).where(
                LlmCall.profile_id.is_(None), LlmCall.purpose.in_(PERSONAL_PURPOSES)
            ),
        ),
    }
    return totals
