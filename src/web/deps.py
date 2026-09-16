"""Request dependencies: database session, signed-in user, owned profile."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.auth import sessions
from src.config import get_settings
from src.db import new_session
from src.models import User


def get_db() -> Iterator[Session]:
    with new_session() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise


def session_secret() -> str:
    settings = get_settings()
    if settings.session_secret is None:
        raise RuntimeError("SESSION_SECRET is not set")
    return settings.session_secret.get_secret_value()


def current_user(request: Request, session: Annotated[Session, Depends(get_db)]) -> User | None:
    """The user behind a valid session cookie, or None.

    Renewal is handled by `middleware.SessionRenewalMiddleware`, which can set the
    cookie on any response; a dependency cannot, because the route decides what
    object it returns.
    """
    token = request.cookies.get(sessions.COOKIE_NAME)
    if token is None:
        return None
    loaded = sessions.load(token, session_secret())
    if loaded is None:
        return None
    user = session.get(User, loaded[0])
    request.state.session_user = user
    return user


CurrentUser = Annotated[User | None, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_user(user: CurrentUser) -> User:
    """Signed-in users only. Anonymous access is a redirect, not an error page."""
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user


SignedInUser = Annotated[User, Depends(require_user)]
