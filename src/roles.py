"""Data access for roles. `profile_id` first, ownership inside the query."""

import uuid
from datetime import date

from sqlalchemy.orm import Session

from src.models import Role
from src.scoping import owned_row, owned_rows


def list_roles(profile_id: uuid.UUID, session: Session, *, active_only: bool = False) -> list[Role]:
    roles = owned_rows(Role, session, profile_id, active_only=active_only)
    return sorted(roles, key=lambda role: role.start_date or date.min, reverse=True)


def get_role(profile_id: uuid.UUID, session: Session, role_id: str | uuid.UUID) -> Role | None:
    return owned_row(Role, session, profile_id, role_id)


def create_role(
    profile_id: uuid.UUID,
    session: Session,
    *,
    employer: str,
    title: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Role:
    role = Role(
        profile_id=profile_id,
        employer=employer.strip(),
        title=title.strip(),
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
    title: str,
    start_date: date | None,
    end_date: date | None,
    active: bool = True,
) -> Role | None:
    role = get_role(profile_id, session, role_id)
    if role is None:
        return None
    role.employer = employer.strip()
    role.title = title.strip()
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
