"""Accounts exist only by CLI (PRD F1: no registration route).

Kept here rather than inside the script so tests can create users the same way the
operator does.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth.passwords import hash_password
from src.auth.rate_limit import normalize
from src.models import Profile, User

MIN_PASSWORD_LENGTH = 12


def create_account(
    session: Session,
    email: str,
    password: str,
    display_name: str,
    lang: str = "es",
) -> tuple[User, Profile]:
    """Create a user and the single profile it owns. Caller commits."""
    address = normalize(email)
    if session.scalar(select(User).where(User.email == address)) is not None:
        raise ValueError(f"{address} already exists")

    user = User(email=address, password_hash=hash_password(password), ui_lang=lang)
    session.add(user)
    session.flush()

    profile = Profile(user_id=user.id, display_name=display_name)
    session.add(profile)
    session.flush()
    return user, profile
