"""Data access for uploaded résumés (PRD F2.6).

The file itself is archived with its SHA-256 the moment it is uploaded, so a bullet
can always be traced back to the document it came from. Career data changes only
when `merged_at` is stamped; `draft` and `gate` are what the review screen renders
in the meantime.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models import Resume
from src.scoping import owned_row, owned_rows, parse_id


def create_resume(
    profile_id: uuid.UUID,
    session: Session,
    *,
    filename: str,
    data: bytes | None,
    sha256: str,
    track_id: uuid.UUID | None = None,
    gate: dict | None = None,
    draft: dict | None = None,
) -> Resume:
    resume = Resume(
        profile_id=profile_id,
        filename=filename,
        file_bytes=data,
        sha256=sha256,
        track_id=track_id,
        gate=gate,
        draft=draft,
    )
    session.add(resume)
    session.flush()
    return resume


def list_resumes(
    profile_id: uuid.UUID, session: Session, *, active_only: bool = False
) -> list[Resume]:
    resumes = owned_rows(Resume, session, profile_id, active_only=active_only)
    return sorted(resumes, key=lambda resume: resume.uploaded_at or datetime.min, reverse=True)


def get_resume(
    profile_id: uuid.UUID, session: Session, resume_id: str | uuid.UUID
) -> Resume | None:
    return owned_row(Resume, session, profile_id, resume_id)


def save_draft(
    profile_id: uuid.UUID, session: Session, resume_id: str | uuid.UUID, draft: dict
) -> Resume | None:
    """Replace the stored draft with the reviewed one; nothing merges here."""
    resume = get_resume(profile_id, session, resume_id)
    if resume is None:
        return None
    resume.draft = draft
    session.flush()
    return resume


def set_resume_active(
    profile_id: uuid.UUID, session: Session, resume_id: str | uuid.UUID, *, active: bool
) -> Resume | None:
    resume = get_resume(profile_id, session, resume_id)
    if resume is None:
        return None
    resume.active = active
    session.flush()
    return resume


def mark_merged(
    profile_id: uuid.UUID, session: Session, resume_id: str | uuid.UUID
) -> Resume | None:
    resume = get_resume(profile_id, session, resume_id)
    if resume is None:
        return None
    resume.merged_at = datetime.now(UTC)
    resume.active = True
    session.flush()
    return resume


def source_document_for_track(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> Resume | None:
    """The most recent active résumé uploaded for a track, or None (PRD F5.1).

    A track built from an upload (F4 creation path 1) carries the document it came
    from, and an analysis of that track is capped by that document's findings — not
    by whatever else happens to sit in the profile. `list_resumes` is newest first,
    so the first match is the most recent one.
    """
    wanted = str(track_id)
    for resume in list_resumes(profile_id, session, active_only=True):
        if resume.track_id is not None and str(resume.track_id) == wanted:
            return resume
    return None



# ---- CVs of a track (PRD F11.1) ----------------------------------------------------

LATEST = "latest"


def _stamp(resume: Resume) -> datetime:
    """When the CV joined the track: `merged_at`, else `uploaded_at` (F11.1).

    SQLite hands back naive datetimes and PostgreSQL aware ones; both are read as UTC
    so the two never meet in one comparison.
    """
    moment = resume.merged_at or resume.uploaded_at or datetime.min
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def track_cvs(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> list[Resume]:
    """The CVs of a track, newest first (F11.1).

    A CV is a merged, active résumé of the track with a stored draft: the draft is what
    the analysis reads, so a row without one is not analysable. The track id is matched
    inside the profile's own rows, so another profile's track yields nothing.
    """
    wanted = str(track_id)
    cvs = [
        resume
        for resume in owned_rows(Resume, session, profile_id, active_only=True)
        if resume.track_id is not None
        and str(resume.track_id) == wanted
        and resume.merged_at is not None
        and resume.draft
    ]
    return sorted(cvs, key=lambda resume: (_stamp(resume), str(resume.id)), reverse=True)


def latest_cv(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> Resume | None:
    """"Último CV de la línea": the track's newest CV, or None when it has none (F11.1)."""
    cvs = track_cvs(profile_id, session, track_id)
    return cvs[0] if cvs else None


def resolve_cv(
    profile_id: uuid.UUID,
    session: Session,
    track_id: str | uuid.UUID,
    choice: str | None,
) -> Resume | None:
    """The CV a form choice means, or None (the route answers 404).

    `choice` is `"latest"` (or empty), resolved to the newest CV now, or a résumé id.
    An id that is not this profile's, not of this track, or not an analysable CV
    resolves to None exactly like an unknown one: a foreign id is not found (F11.11-8).
    """
    cvs = track_cvs(profile_id, session, track_id)
    if not choice or choice == LATEST:
        return cvs[0] if cvs else None
    key = parse_id(choice)
    if key is None:
        return None
    return next((resume for resume in cvs if resume.id == key), None)
