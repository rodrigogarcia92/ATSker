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
from src.scoping import owned_row, owned_rows


def create_resume(
    profile_id: uuid.UUID,
    session: Session,
    *,
    filename: str,
    data: bytes,
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

