"""Loading a row owned by the signed-in user's profile (PRD F1).

Every career-data query filters by `profile_id` inside the WHERE clause rather than
checking ownership afterwards, so a missed check cannot exist: a row belonging to
another profile is simply not found, and not-found is what the UI reports.
"""

import uuid
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Base

_T = TypeVar("_T", bound=Base)


def parse_id(value: str | uuid.UUID) -> uuid.UUID | None:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        return None


def owned_row(
    model: type[_T],
    session: Session,
    profile_id: uuid.UUID,
    row_id: str | uuid.UUID,
) -> _T | None:
    """The row only if this profile owns it; None covers both wrong-owner and absent."""
    key = parse_id(row_id)
    if key is None:
        return None
    return session.scalar(select(model).where(model.id == key, model.profile_id == profile_id))


def owned_rows(
    model: type[_T],
    session: Session,
    profile_id: uuid.UUID,
    *,
    active_only: bool = False,
) -> list[_T]:
    stmt = select(model).where(model.profile_id == profile_id)
    if active_only and hasattr(model, "active"):
        stmt = stmt.where(model.active.is_(True))
    return list(session.scalars(stmt))
