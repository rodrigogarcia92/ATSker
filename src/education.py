"""Data access for education entries.

Not in PRD 6's table list, but F2's review screen extracts education and F7 renders
it, so it needs somewhere to live.
"""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from src.models import Education
from src.scoping import owned_row, owned_rows


def list_educations(profile_id: uuid.UUID, session: Session) -> list[Education]:
    entries = owned_rows(Education, session, profile_id)
    return sorted(entries, key=lambda entry: entry.end_date or date.min, reverse=True)


def get_education(
    profile_id: uuid.UUID, session: Session, education_id: str | uuid.UUID
) -> Education | None:
    return owned_row(Education, session, profile_id, education_id)


def create_education(
    profile_id: uuid.UUID,
    session: Session,
    *,
    institution: str,
    degree: str | None = None,
    field: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Education:
    entry = Education(
        profile_id=profile_id,
        institution=institution.strip(),
        degree=(degree or "").strip() or None,
        field=(field or "").strip() or None,
        start_date=start_date,
        end_date=end_date,
    )
    session.add(entry)
    session.flush()
    return entry


def update_education(
    profile_id: uuid.UUID,
    session: Session,
    education_id: str | uuid.UUID,
    *,
    institution: str,
    degree: str | None,
    field: str | None,
    start_date: date | None,
    end_date: date | None,
) -> Education | None:
    entry = get_education(profile_id, session, education_id)
    if entry is None:
        return None
    entry.institution = institution.strip()
    entry.degree = (degree or "").strip() or None
    entry.field = (field or "").strip() or None
    entry.start_date = start_date
    entry.end_date = end_date
    session.flush()
    return entry


def delete_education(
    profile_id: uuid.UUID, session: Session, education_id: str | uuid.UUID
) -> bool:
    entry = get_education(profile_id, session, education_id)
    if entry is None:
        return False
    session.delete(entry)
    session.flush()
    return True
