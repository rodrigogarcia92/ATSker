"""Session cookie attributes (PRD F1).

`Secure` is on whenever the app believes it is in production — it is set there by
the deploy. Locally the app is served over http, and a browser silently drops a
Secure cookie, which would make login impossible to test.
"""

from fastapi import Response

from src.auth.sessions import COOKIE_NAME, SESSION_MAX_AGE
from src.config import get_settings


def _secure() -> bool:
    return get_settings().env == "production"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(),
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_secure(),
    )
