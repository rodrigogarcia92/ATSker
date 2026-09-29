"""Data access for the summary pool (PRD F2.7). `profile_id` first, as everywhere.

Summaries are soft-deleted like bullets: a stored report that cited one must still
render it, so deactivation is the delete and there is no hard-delete function here.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models import Summary
from src.scoping import owned_row, owned_rows


def list_summaries(
    profile_id: uuid.UUID,
    session: Session,
    *,
    lang: str | None = None,
    active_only: bool = True,
) -> list[Summary]:
    """The pool in creation order; `lang` narrows, `active_only` hides retired rows.

    Creation order, oldest first, and deterministic: the pickers append a summary the
    user just wrote at the bottom, and two rows can never swap places between two
    reads. `create_summary` stamps a microsecond timestamp, so the order really is the
    order they were written in; a row that predates that (or somehow ties) falls back
    to its id, which is arbitrary but stable — never "whatever the database returned".
    """
    entries = owned_rows(Summary, session, profile_id, active_only=active_only)
    if lang is not None:
        entries = [entry for entry in entries if entry.lang == lang]
    return sorted(entries, key=lambda entry: (_comparable(entry.created_at), str(entry.id)))


def _comparable(value: datetime | None) -> datetime:
    """A naive-UTC datetime, so a freshly created aware row sorts with stored naive ones.

    sqlite hands naive rows back; a row created in this session still carries the
    `datetime.now(UTC)` it was given, and comparing the two would raise (G.1).
    """
    if value is None:
        return datetime.min
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def get_summary(
    profile_id: uuid.UUID, session: Session, summary_id: str | uuid.UUID
) -> Summary | None:
    return owned_row(Summary, session, profile_id, summary_id)


def create_summary(
    profile_id: uuid.UUID,
    session: Session,
    *,
    text: str,
    lang: str = "es",
    source_resume_id: uuid.UUID | None = None,
) -> Summary:
    entry = Summary(
        profile_id=profile_id,
        lang=lang,
        text=" ".join(text.split()).strip(),
        source_resume_id=source_resume_id,
        # Explicit and microsecond-precise: the pool is listed in creation order, and
        # the database's own default has only second resolution on SQLite, which made
        # two rows written in the same second order-ambiguous (G.1).
        created_at=datetime.now(UTC),
    )
    session.add(entry)
    session.flush()
    return entry


def update_summary(
    profile_id: uuid.UUID,
    session: Session,
    summary_id: str | uuid.UUID,
    *,
    text: str,
    lang: str,
) -> Summary | None:
    """Editing the pool row changes every track whose slot references it (F4.1)."""
    entry = get_summary(profile_id, session, summary_id)
    if entry is None:
        return None
    entry.text = " ".join(text.split()).strip()
    entry.lang = lang
    session.flush()
    return entry


def set_summary_active(
    profile_id: uuid.UUID, session: Session, summary_id: str | uuid.UUID, *, active: bool
) -> Summary | None:
    """Deactivate rather than delete, so nothing historical breaks."""
    entry = get_summary(profile_id, session, summary_id)
    if entry is None:
        return None
    entry.active = active
    session.flush()
    return entry
