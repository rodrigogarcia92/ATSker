"""Handing an attempt's new material to the F2.5 review (PRD F10.7, C.3).

Nothing enters the master database without review, and the review is the F2.5 one: the
same `diff_draft` labels the candidates and the same create/update helpers write them.
What is different is the source — an attempt's draft, not a résumé row — and the
destination, which the user chooses afterwards and which is **never** a track by
default: "este puesto", "otro puesto", "nuevo puesto" or "solo mi material".

Only new or changed bullets travel: a matched bullet is already master data, so the
merge has nothing to write for it. New skills go to the profile's pool.
"""

import uuid

from sqlalchemy.orm import Session

from src.bullets import create_bullet, update_bullet
from src.ingest.draft import ResumeDraft
from src.ingest.merge import MergePlan, Selections, diff_draft
from src.models import Application, Profile
from src.roles import create_role
from src.tracks import create_track, set_track_bullets, track_bullets

DESTINATIONS = ("solo", "este", "otro", "nuevo")


def attempt_draft(report: dict) -> ResumeDraft:
    """The file's new material: temporary bullets and the new skills (F10.7).

    A bullet the attempt matched to a master row is dropped here — the review cannot
    offer what the database already holds. Educations and certifications do not travel:
    F10.7 hands over bullets and skills.
    """
    draft = dict(report.get("draft") or {})
    temporary = {
        str(snapshot.get("text") or "")
        for snapshot in report.get("bullets") or []
        if snapshot.get("temporary")
    }
    roles = []
    for role in draft.get("roles") or []:
        bullets = [
            bullet
            for bullet in (role.get("bullets") or [])
            if str(bullet.get("text") or "") in temporary
        ]
        if bullets:
            roles.append({**role, "bullets": bullets})
    skills = [str(skill) for skill in (report.get("flags") or {}).get("skills") or []]
    return ResumeDraft.model_validate(
        {
            **draft,
            "roles": roles,
            "skills": skills,
            "educations": [],
            "certifications": [],
        }
    )


def merge_plan(profile_id: uuid.UUID, session: Session, draft: ResumeDraft) -> MergePlan:
    """The F2.5 diff over the reduced draft: new, changed and unchanged, labelled."""
    return diff_draft(profile_id, session, draft)


def _columns(language: str, text: str) -> tuple[str | None, str | None]:
    """`(text_en, text_es)` — the text goes into its own language's column."""
    return (text, None) if language == "en" else (None, text)


def every_selection(plan: MergePlan) -> Selections:
    """Everything the plan proposes, which is what a confirmed review applies."""
    return Selections(
        roles=frozenset(range(len(plan.roles))),
        bullets=frozenset(
            (role_index, bullet_index)
            for role_index, role in enumerate(plan.roles)
            for bullet_index, _bullet in enumerate(role.bullets)
        ),
        educations=frozenset(),
        certifications=frozenset(),
        skills=frozenset(range(len(plan.skills))),
    )


def apply_attempt_merge(
    profile_id: uuid.UUID,
    session: Session,
    *,
    draft: ResumeDraft,
    plan: MergePlan,
    selections: Selections | None = None,
) -> dict[str, object]:
    """Write the confirmed candidates. **No track is touched here** (F10.7): the
    destination is a separate, explicit choice."""
    chosen = selections or every_selection(plan)
    counts = {
        "roles_created": 0,
        "roles_updated": 0,
        "bullets_created": 0,
        "bullets_updated": 0,
        "skills_added": 0,
    }
    created: list[str] = []
    for role_index, role in enumerate(plan.roles):
        if role_index not in chosen.roles:
            continue
        role_id = role.existing_id
        if role_id is None:
            text_en, text_es = _columns(draft.language, role.title)
            created_role = create_role(
                profile_id,
                session,
                employer=role.employer,
                title_es=text_es,
                title_en=text_en,
                start_date=role.start_date,
                end_date=role.end_date,
                language=draft.language,
            )
            role_id = created_role.id
            counts["roles_created"] += 1
        for bullet_index, candidate in enumerate(role.bullets):
            if (role_index, bullet_index) not in chosen.bullets:
                continue
            text_en, text_es = _columns(draft.language, candidate.text)
            if candidate.label == "new":
                bullet = create_bullet(
                    profile_id,
                    session,
                    role_id=role_id,
                    text_en=text_en,
                    text_es=text_es,
                    chips=candidate.chips,
                )
                created.append(str(bullet.id))
                counts["bullets_created"] += 1
            elif candidate.existing_id is not None:
                update_bullet(
                    profile_id,
                    session,
                    candidate.existing_id,
                    text_en=text_en,
                    text_es=text_es,
                    chips=candidate.chips,
                )
                counts["bullets_updated"] += 1

    profile = session.get(Profile, profile_id)
    if profile is not None:
        for index, candidate in enumerate(plan.skills):
            if index not in chosen.skills:
                continue
            if candidate.canonical not in profile.skills:
                profile.skills = [*profile.skills, candidate.canonical]
                counts["skills_added"] += 1
    session.flush()
    return {"counts": counts, "bullet_ids": created}


def apply_destination(
    profile_id: uuid.UUID,
    session: Session,
    *,
    application: Application,
    bullet_ids: list[str],
    choice: str,
    track_id: str | None = None,
    new_name: str | None = None,
) -> uuid.UUID | None:
    """Where the merged bullets go (F10.7): a track only when one was chosen.

    `solo` (the default) writes nothing here, `este` appends to the analysis's track,
    `otro` to the chosen one, `nuevo` to a track created for the purpose. Appending
    never replaces a selection.
    """
    if choice not in DESTINATIONS or not bullet_ids:
        return None
    ids = [uuid.UUID(value) for value in bullet_ids]
    if choice == "este":
        target = application.track_id
    elif choice == "otro":
        target = uuid.UUID(track_id) if track_id else None
    elif choice == "nuevo":
        name = (new_name or "").strip()
        if not name:
            return None
        created = create_track(profile_id, session, name=name)
        set_track_bullets(profile_id, session, created.id, ids)
        session.flush()
        return created.id
    else:
        return None
    if target is None:
        return None
    existing = [bullet.id for bullet in track_bullets(profile_id, session, target)]
    wanted = [*existing, *[value for value in ids if value not in existing]]
    set_track_bullets(profile_id, session, target, wanted)
    session.flush()
    return target
