"""Data access for analyses (PRD F8, F9).

`profile_id` comes first and ownership is part of the query, never a check after
the fact: another profile's report is simply not found.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from src.models import Application, Track
from src.normalize.text import fold
from src.scoping import owned_row, owned_rows


def create_application(
    profile_id: uuid.UUID,
    session: Session,
    *,
    jd_text: str,
    jd_hash: str,
    report: dict,
    weights_version: str,
    prompt_versions: dict,
    token_cost_usd: Decimal,
    company: str | None = None,
    title: str | None = None,
    track_id: uuid.UUID | None = None,
    scan_readability: dict | None = None,
) -> Application:
    """Persist one analysis. The schema exists from the first real application (F8)."""
    application = Application(
        profile_id=profile_id,
        company=company,
        title=title,
        jd_text=jd_text,
        jd_hash=jd_hash,
        report=report,
        weights_version=weights_version,
        prompt_versions=prompt_versions,
        token_cost_usd=token_cost_usd,
        track_id=track_id,
        scan_readability=scan_readability,
    )
    session.add(application)
    session.flush()
    return application


def get_application(
    profile_id: uuid.UUID, session: Session, application_id: str | uuid.UUID
) -> Application | None:
    return owned_row(Application, session, profile_id, application_id)


# The five outcomes F9 lists. A value outside this set is refused, never stored.
OUTCOMES = ("no_reply", "screen", "interview", "offer", "rejected")

# What the history table can be sorted by, and the default when the value is unknown:
# a bad `?sort=` is a fallback, not an error (F9's table is a view, not an API).
HISTORY_SORTS = ("date", "score", "company", "title", "track", "outcome")


def set_application_outcome(
    profile_id: uuid.UUID,
    session: Session,
    application_id: str | uuid.UUID,
    *,
    outcome: str,
) -> Application | None:
    """Record what happened after sending one application (F9)."""
    application = get_application(profile_id, session, application_id)
    if application is None:
        return None
    application.outcome = outcome
    session.flush()
    return application


def list_applications(
    profile_id: uuid.UUID,
    session: Session,
    *,
    sort: str = "date",
    direction: str = "desc",
) -> list[dict[str, object]]:
    """One row per analysis for the history table, sorted server-side (F9).

    Sorting happens here rather than in SQL because two of the columns live elsewhere:
    the score is inside the stored report and the track is a row of its own. The table
    is per profile and small, and these are the values the user sorts by — a number and
    a name, not a JSON path.
    """
    key = sort if sort in HISTORY_SORTS else "date"
    reverse = direction != "asc"
    rows: list[dict[str, object]] = []
    for application in owned_rows(Application, session, profile_id):
        report = application.report or {}
        score = report.get("score") or {}
        snapshot = report.get("track") or {}
        track = session.get(Track, application.track_id) if application.track_id else None
        rows.append(
            {
                "id": application.id,
                "created_at": application.created_at,
                "company": application.company or "",
                "title": application.title or "",
                # The track's current name, or the name the report recorded when the
                # track has since been renamed or deactivated (F4).
                "track": track.name if track is not None else str(snapshot.get("name") or ""),
                "score": score.get("capped"),
                "weights_version": application.weights_version,
                "outcome": application.outcome,
            }
        )

    if key == "score":
        # An analysis with no score at all sorts last in both directions: it is not a
        # zero, and pretending otherwise would put it above real failures.
        scored = [row for row in rows if row["score"] is not None]
        unscored = [row for row in rows if row["score"] is None]
        scored.sort(key=lambda row: (row["score"], str(row["title"])), reverse=reverse)
        return scored + unscored

    def order_key(row: dict[str, object]):
        if key == "date":
            return (row["created_at"] or datetime.min, str(row["id"]))
        return (fold(str(row[key])), row["created_at"] or datetime.min)

    return sorted(rows, key=order_key, reverse=reverse)
