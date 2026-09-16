"""Data access for profiles.

Every function here takes `profile_id` first and reaches no further than the
session's own user (PRD F1). An id arriving from a URL, query string, or form is
never sufficient on its own: the ownership filter is part of the query, not a
check performed afterwards.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Profile, User


def get_profile(profile_id: uuid.UUID | str, session: Session, user: User) -> Profile | None:
    """The profile only if the signed-in user owns it."""
    try:
        key = uuid.UUID(str(profile_id))
    except ValueError:
        return None
    return session.scalar(select(Profile).where(Profile.id == key, Profile.user_id == user.id))


def get_own_profile(session: Session, user: User) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.user_id == user.id))
