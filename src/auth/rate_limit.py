"""Per-username login rate limit (PRD F1: 5 failures per 15 minutes)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.models import LoginAttempt

LIMIT = 5
WINDOW = timedelta(minutes=15)


def normalize(username: str) -> str:
    return username.strip().lower()


def is_rate_limited(session: Session, username: str, now: datetime | None = None) -> bool:
    since = (now or datetime.now(UTC)) - WINDOW
    counted = session.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(LoginAttempt.username == normalize(username), LoginAttempt.attempted_at >= since)
    )
    return (counted or 0) >= LIMIT


def record_failure(session: Session, username: str, now: datetime | None = None) -> None:
    session.add(LoginAttempt(username=normalize(username), attempted_at=now or datetime.now(UTC)))


def clear_failures(session: Session, username: str) -> None:
    session.execute(delete(LoginAttempt).where(LoginAttempt.username == normalize(username)))
