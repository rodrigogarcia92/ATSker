"""Login: the only place a session is created."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.auth import rate_limit
from src.auth.passwords import DUMMY_HASH, verify_password
from src.models import User


class RateLimitedError(Exception):
    """Raised when this username has failed too often inside the window."""


def authenticate(
    session: Session, email: str, password: str, now: datetime | None = None
) -> User | None:
    """Return the user on success, None on bad credentials; commit exactly once either way."""
    if rate_limit.is_rate_limited(session, email, now):
        raise RateLimitedError

    user = session.scalar(select(User).where(User.email == rate_limit.normalize(email)))
    password_hash = user.password_hash if user is not None else DUMMY_HASH

    if user is None or not verify_password(password_hash, password):
        rate_limit.record_failure(session, email, now)
        session.commit()
        return None

    rate_limit.clear_failures(session, email)
    session.commit()
    return user
