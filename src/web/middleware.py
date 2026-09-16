"""Sliding session renewal (PRD F1: 30-day expiry, renewed on use).

The token is re-issued once a week of active use has passed. This runs in
middleware rather than in a dependency because only middleware can attach a
header to whatever object the route ends up returning; it validates the signature
and never touches the database, so the cost is a signature check.
"""

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from src.auth import sessions
from src.web.cookies import set_session_cookie
from src.web.deps import session_secret


async def renew_session(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)

    token = request.cookies.get(sessions.COOKIE_NAME)
    if token is None or response.status_code >= 400:
        return response

    loaded = sessions.load(token, session_secret())
    if loaded is not None and sessions.needs_renewal(loaded[1]):
        set_session_cookie(response, sessions.issue(loaded[0], session_secret()))
    return response
