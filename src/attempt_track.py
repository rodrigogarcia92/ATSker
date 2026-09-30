"""The ephemeral track (PRD F10.3 step 3, A4, B.2): the file read as a CV.

Bullet matching reuses the F2.5 diff: a bullet whose text is the same after
normalisation, or which the diff labels unchanged, reuses its master row — id and all —
which is what makes an unchanged export reproduce the analysis's grading input exactly.
A new or changed bullet gets a temporary id and a snapshot of its text.

Role matching is the diff's (folded employer and title) plus one step of its own: a
tailored CV retitles a role, but the job is the same one when the employer and the
start month are the same. A role that still matches nothing is scored from the file,
as a transient `Role` that is never added to the session (D5).

The document is built in the posting's language with the same shape
`documents.track_document` produces, so the keyword scan, the recruiter search and the
grader all read the file as they read a track.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.documents import (
    DocumentUnit,
    document_headline,
    document_summary,
    track_document,
)
from src.ingest.draft import DraftRole, ResumeDraft, parse_partial_date
from src.ingest.merge import BulletCandidate, _bullet_candidates, diff_draft
from src.models import Application, Bullet, Role
from src.normalize.text import fold
from src.roles import list_roles
from src.tracks import get_track


@dataclass(frozen=True)
class BulletSnapshot:
    """One file bullet as the attempt read it: its id, its text, and whether the id
    is temporary (a new or changed bullet) rather than a master row's (F10.3 step 3)."""

    id: str
    temporary: bool
    role_id: str
    text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "temporary": self.temporary,
            "role_id": self.role_id,
            "text": self.text,
        }


@dataclass(frozen=True)
class EphemeralTrack:
    """The file scored as a track, without writing a track (A4).

    `bullets` are the master rows for unchanged text and transient rows for new or
    changed text; `document` is built in the posting's language from the same shape
    `track_document` produces, so an unchanged export is the analysis's own document.
    `snapshots` keep the file's wording per bullet for the report and the flags.
    `roles` are the transient roles of the file's unmatched jobs, which the scorer
    counts like any other role; `role_matching` says how each file role was matched
    (titles only, no bullet text) for the reviewer's diagnostic.
    """

    bullets: tuple[Bullet, ...]
    document: tuple[DocumentUnit, ...]
    snapshots: tuple[BulletSnapshot, ...]
    roles: tuple[Role, ...] = ()
    role_matching: tuple[dict[str, object], ...] = ()


def _transient_bullet(
    profile_id: uuid.UUID,
    role_id: uuid.UUID,
    column: str,
    text: str,
    chips: Sequence[str],
) -> Bullet:
    """A bullet that exists only for this run: never added to a session, never stored.

    `id` is set so a citation can name it; `role_id` is a master role when the file's
    role matched one, and a fresh id otherwise (an unmatched role is not master data,
    so it is not counted and the F10.5 diff flags it).
    """
    values: dict[str, object] = {"text_en": None, "text_es": None, column: text}
    return Bullet(
        id=uuid.uuid4(),
        profile_id=profile_id,
        role_id=role_id,
        skills=list(chips),
        metrics=[],
        pending_terms=[],
        active=True,
        **values,  # type: ignore[arg-type]
    )


def _start_month(value: date | None) -> tuple[int, int] | None:
    return (value.year, value.month) if value is not None else None


def _role_by_start(
    raw: DraftRole, masters: Sequence[Role], claimed: set[uuid.UUID]
) -> Role | None:
    """The one master role with the file role's employer and start month, if any.

    Two or more candidates are ambiguous and match nothing; a file role with no start
    date matches nothing; a master role another file role already took is not offered
    a second time.
    """
    start = _start_month(parse_partial_date(raw.start_date))
    employer = fold(raw.employer)
    if start is None or not employer:
        return None
    candidates = [
        role
        for role in masters
        if fold(role.employer) == employer and _start_month(role.start_date) == start
    ]
    if len(candidates) != 1 or candidates[0].id in claimed:
        return None
    return candidates[0]


def ephemeral_track(
    profile_id: uuid.UUID,
    session: Session,
    *,
    application: Application,
    draft: ResumeDraft,
) -> EphemeralTrack:
    """Match the file's bullets to master bullets and build the document (A4/F10.3).

    An **unchanged** bullet — the same text after normalisation, or the F2.5 diff's
    unchanged label — reuses the master row, id and all: that is what makes an
    unchanged export reproduce the analysis's grading input exactly. A new or changed
    bullet gets a temporary id and its text is snapshotted. The headline, summary and
    skills come from the master unless the file's differ.
    """
    track = (
        get_track(profile_id, session, application.track_id)
        if application.track_id
        else None
    )
    jd_dict = application.report.get("jd") if application.report else None
    lang = str((jd_dict or {}).get("language") or draft.language or "es")
    column = "text_en" if (draft.language or "es") == "en" else "text_es"

    plan = diff_draft(profile_id, session, draft)
    master = {
        str(bullet.id): bullet for bullet in list_bullets(profile_id, session, active_only=False)
    }
    masters = list_roles(profile_id, session, active_only=True)
    claimed = {role.existing_id for role in plan.roles if role.existing_id is not None}
    bullets: list[Bullet] = []
    snapshots: list[BulletSnapshot] = []
    transient_roles: list[Role] = []
    role_matching: list[dict[str, object]] = []
    for raw, role in zip(draft.roles, plan.roles, strict=True):
        candidates: Sequence[BulletCandidate] = role.bullets
        if role.existing_id is not None:
            role_id, by = role.existing_id, "employer_title"
        else:
            matched = _role_by_start(raw, masters, claimed)
            if matched is not None:
                # The same job under another title: its bullets meet the master role's.
                claimed.add(matched.id)
                role_id, by = matched.id, "employer_start"
                candidates = _bullet_candidates(
                    raw.bullets, [b for b in master.values() if b.role_id == matched.id]
                )
            else:
                # Not master data, but its citations still count in Experience: a
                # transient role with the file's own employer, title and dates.
                fresh = Role(
                    id=uuid.uuid4(),
                    profile_id=profile_id,
                    employer=role.employer,
                    title=role.title,
                    start_date=role.start_date,
                    end_date=role.end_date,
                    active=True,
                )
                transient_roles.append(fresh)
                role_id, by = fresh.id, "file_only"
        role_matching.append(
            {
                "file_title": role.title,
                "matched_role_id": str(role_id) if by != "file_only" else None,
                "by": by,
            }
        )
        for candidate in candidates:
            existing = master.get(str(candidate.existing_id)) if candidate.existing_id else None
            if candidate.label == "unchanged" and existing is not None:
                bullets.append(existing)
                snapshots.append(
                    BulletSnapshot(
                        str(existing.id), False, str(existing.role_id), candidate.text
                    )
                )
            else:
                fresh = _transient_bullet(
                    profile_id, role_id, column, candidate.text, candidate.chips
                )
                bullets.append(fresh)
                snapshots.append(
                    BulletSnapshot(str(fresh.id), True, str(role_id), candidate.text)
                )

    base = track_document(profile_id, session, track, lang)
    master_headline = (document_headline(base) or "").strip()
    master_summary = (document_summary(base) or "").strip()
    master_skills = [unit.text for unit in base if unit.kind == "skills_list"]

    headline = (draft.headline or "").strip()
    summary = (draft.summary or "").strip()
    document = track_document(
        profile_id,
        session,
        track,
        lang,
        bullets=bullets,
        headline=headline if headline and headline != master_headline else None,
        summary_text=summary if summary and summary != master_summary else None,
        skills=(
            list(draft.skills)
            if track is not None and list(draft.skills) != master_skills
            else None
        ),
    )
    return EphemeralTrack(
        bullets=tuple(bullets),
        document=tuple(document),
        snapshots=tuple(snapshots),
        roles=tuple(transient_roles),
        role_matching=tuple(role_matching),
    )
