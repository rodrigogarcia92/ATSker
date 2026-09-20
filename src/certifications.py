"""Data access for certifications (PRD F2/F3). `profile_id` first, as everywhere."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from src.models import Certification
from src.scoping import owned_row, owned_rows


def list_certifications(profile_id: uuid.UUID, session: Session) -> list[Certification]:
    entries = owned_rows(Certification, session, profile_id)
    return sorted(entries, key=lambda entry: entry.issued_date or date.min, reverse=True)


def get_certification(
    profile_id: uuid.UUID, session: Session, certification_id: str | uuid.UUID
) -> Certification | None:
    return owned_row(Certification, session, profile_id, certification_id)


def create_certification(
    profile_id: uuid.UUID,
    session: Session,
    *,
    name: str,
    issuer: str | None = None,
    issued_date: date | None = None,
    expiry_date: date | None = None,
    credential_id: str | None = None,
    credential_url: str | None = None,
) -> Certification:
    entry = Certification(
        profile_id=profile_id,
        name=name.strip(),
        issuer=(issuer or "").strip() or None,
        issued_date=issued_date,
        expiry_date=expiry_date,
        credential_id=(credential_id or "").strip() or None,
        credential_url=(credential_url or "").strip() or None,
    )
    session.add(entry)
    session.flush()
    return entry


def update_certification(
    profile_id: uuid.UUID,
    session: Session,
    certification_id: str | uuid.UUID,
    *,
    name: str,
    issuer: str | None,
    issued_date: date | None,
    expiry_date: date | None,
    credential_id: str | None,
    credential_url: str | None,
    active: bool = True,
) -> Certification | None:
    entry = get_certification(profile_id, session, certification_id)
    if entry is None:
        return None
    entry.name = name.strip()
    entry.issuer = (issuer or "").strip() or None
    entry.issued_date = issued_date
    entry.expiry_date = expiry_date
    entry.credential_id = (credential_id or "").strip() or None
    entry.credential_url = (credential_url or "").strip() or None
    entry.active = active
    session.flush()
    return entry


def set_certification_active(
    profile_id: uuid.UUID, session: Session, certification_id: str | uuid.UUID, *, active: bool
) -> Certification | None:
    """Deactivate rather than delete, so nothing historical breaks."""
    entry = get_certification(profile_id, session, certification_id)
    if entry is None:
        return None
    entry.active = active
    session.flush()
    return entry