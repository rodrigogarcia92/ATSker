"""The logged-in home's data (PRD §12.8): the three cards, the last report, the activity.

A view module, like `cv_pane`: it returns plain values — numbers, names, timestamps —
and `home.html` composes every sentence with `t`, so no user-visible string is built
here and both languages stay in `strings.py`. Reads only; it makes no model call.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.applications import list_applications
from src.attempts import MAX_ATTEMPTS, counted_attempts
from src.models import ApplicationAttempt, Resume
from src.resumes import list_resumes
from src.tracks import list_tracks

# How many events §12.8's "recent activity" names.
ACTIVITY_LIMIT = 5


def home_view(profile_id: uuid.UUID, session: Session) -> dict[str, object]:
    """Everything `home.html` shows, for this profile only (F1).

    One read per surface: the analyses (newest first, the row the history shows), the
    CVs, the tracks, and the attempts that finished. An empty profile returns the same
    shape with `None`s, so the template has one branch per card and not two.
    """
    analyses = list_applications(profile_id, session)
    resumes = list_resumes(profile_id, session)
    # "CV más reciente" is a CV of a track (F11.1): a file that was never merged into
    # the career data is not something the form could score.
    cvs = [resume for resume in resumes if resume.merged_at is not None]
    last = analyses[0] if analyses else None
    newest_cv = cvs[0] if cvs else (resumes[0] if resumes else None)
    return {
        "analyses": analyses,
        "last": last,
        "attempts": (
            counted_attempts(profile_id, session, last["id"]) if last is not None else 0
        ),
        "max_attempts": MAX_ATTEMPTS,
        "imported_at": resumes[0].uploaded_at if resumes else None,
        "tracks": len(list_tracks(profile_id, session)),
        "cv_name": newest_cv.filename if newest_cv is not None else None,
        "activity": _activity(profile_id, session, analyses, resumes),
    }


def _activity(
    profile_id: uuid.UUID,
    session: Session,
    analyses: list[dict[str, object]],
    resumes: list[Resume],
    limit: int = ACTIVITY_LIMIT,
) -> list[dict[str, object]]:
    """The newest events of this profile, in the order §12.8's list reads them.

    Three kinds, each with the moment it happened: an analysis, a CV import, and a
    finished attempt. A failed or still-running attempt is not an event worth naming,
    and a CV saved from an attempt (F11.7) is not an import — it has no upload.
    """
    by_id = {row["id"]: row for row in analyses}
    events: list[dict[str, object]] = [
        {
            "kind": "analysis",
            "at": row["created_at"],
            "subject": row["title"] or row["track"],
            "company": row["company"],
        }
        for row in analyses
    ]
    events += [
        {"kind": "import", "at": resume.uploaded_at, "filename": resume.filename}
        for resume in resumes
        if resume.source_attempt_id is None
    ]
    attempts = session.scalars(
        select(ApplicationAttempt)
        .where(
            ApplicationAttempt.profile_id == profile_id,
            ApplicationAttempt.active.is_(True),
            ApplicationAttempt.status == "done",
        )
        .order_by(ApplicationAttempt.created_at)
    )
    for attempt in attempts:
        row = by_id.get(attempt.application_id) or {}
        events.append(
            {
                "kind": "attempt",
                "at": attempt.created_at,
                "number": attempt.attempt_no,
                "subject": row.get("title") or row.get("track"),
                "company": row.get("company"),
            }
        )
    # Newest first. A timestamp from a driver that returns naive datetimes still orders
    # against the others of the same read, which is all this list needs.
    events.sort(key=lambda event: _stamp(event["at"]), reverse=True)
    return events[:limit]


def _stamp(value: object) -> float:
    return value.timestamp() if isinstance(value, datetime) else 0.0
