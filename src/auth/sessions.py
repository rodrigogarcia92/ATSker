"""Signed session cookies.

The cookie carries only the user id, signed with `SESSION_SECRET`; there is no
server-side session table to keep alive (and none to keep Neon awake). Itsdangerous
timestamps the payload, which gives both the 30-day absolute expiry and the sliding
renewal: a session older than `RENEW_AFTER` is re-issued with a fresh timestamp.
"""

import uuid
from datetime import UTC, datetime

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "atsker_session"
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days (PRD F1)
RENEW_AFTER = 7 * 24 * 60 * 60  # re-issue once a week of use has passed
_SALT = "atsker.session"


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt=_SALT)


def issue(user_id: uuid.UUID, secret: str) -> str:
    return _serializer(secret).dumps({"uid": str(user_id)})


def load(token: str, secret: str, max_age: int = SESSION_MAX_AGE) -> tuple[uuid.UUID, float] | None:
    """Return the user id and the moment the token was signed, or None if invalid."""
    try:
        payload, signed_at = _serializer(secret).loads(
            token, max_age=max_age, return_timestamp=True
        )
    except (BadSignature, SignatureExpired):
        return None
    try:
        return uuid.UUID(payload["uid"]), signed_at.timestamp()
    except (KeyError, TypeError, ValueError):
        return None


def needs_renewal(signed_at: float, now: datetime | None = None) -> bool:
    current = (now or datetime.now(UTC)).timestamp()
    return current - signed_at > RENEW_AFTER
