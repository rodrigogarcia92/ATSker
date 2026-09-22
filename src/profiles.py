"""Data access for profiles.

Every function here takes `profile_id` first and reaches no further than the
session's own user (PRD F1). An id arriving from a URL, query string, or form is
never sufficient on its own: the ownership filter is part of the query, not a
check performed afterwards.
"""

import uuid
from collections.abc import Sequence

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


def update_profile(
    profile_id: uuid.UUID | str,
    session: Session,
    user: User,
    *,
    display_name: str,
    headline: str | None,
    summary: str | None,
    standing_risks: Sequence[str] = (),
) -> Profile | None:
    profile = get_profile(profile_id, session, user)
    if profile is None:
        return None
    profile.display_name = display_name.strip()
    profile.headline = (headline or "").strip() or None
    profile.summary = (summary or "").strip() or None
    # F6.1's standing risks, user-entered rows. Without this editor the gap analysis
    # would read an empty array forever.
    profile.standing_risks = [risk.strip() for risk in standing_risks if risk.strip()]
    session.flush()
    return profile
