"""Data access for analyses (PRD F8, F9).

`profile_id` comes first and ownership is part of the query, never a check after
the fact: another profile's report is simply not found.
"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from src.letters import get_letter
from src.models import Application, Track
from src.normalize.text import fold
from src.scoping import owned_row, owned_rows
from src.score import SUB_SCORES


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
    scan_boolean: dict | None = None,
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
        scan_boolean=scan_boolean,
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

# What "no outcome recorded" is in this schema: the column is NOT NULL and defaults to
# `no_reply`, which is exactly the state F.1 nudges about — nothing has come back yet.
NO_OUTCOME = ("no_reply",)

# The nudge's window is a presentation setting, never a scoring or storage rule (F.1).
STALE_DAYS = 14

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


def _sub_scores(score: Mapping[str, Any]) -> dict[str, int | None]:
    """F9's four sub-scores as integers 0–100, or None where the report stored none.

    Sub-scores are stored as 0–1 and multiplied by 100 only for display (PRD §12.1);
    a report from before a sub-score existed, or scored under weights that did not
    have it, keeps a None and the table shows "—".
    """
    stored = score.get("sub_scores") or {}
    values: dict[str, int | None] = {}
    for name in SUB_SCORES:
        entry = stored.get(name)
        value = entry.get("value") if isinstance(entry, Mapping) else None
        values[name] = round(float(value) * 100) if value is not None else None
    return values


def _readability_scan(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Scan A (F5.1) as a verdict for the table: the cap and the finding count."""
    if not payload:
        return None
    return {"cap": payload.get("cap"), "findings": len(payload.get("findings") or [])}


def _boolean_scan(payload: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Scan B (F5.2): whether the track came back in every derived query.

    No queries derived — an analysis stored before Scan B existed — is None, not a
    pass: nothing was searched, which is not the same as being findable.
    """
    if not payload:
        return None
    queries = payload.get("queries") or []
    if not queries:
        return None
    return {"queries": len(queries), "passed": all(bool(q.get("passed")) for q in queries)}


def list_applications(
    profile_id: uuid.UUID,
    session: Session,
    *,
    sort: str = "date",
    direction: str = "desc",
    outcome: str | None = None,
) -> list[dict[str, object]]:
    """One row per analysis for the history table, sorted server-side (F9).

    Sorting happens here rather than in SQL because two of the columns live elsewhere:
    the score is inside the stored report and the track is a row of its own. The table
    is per profile and small, and these are the values the user sorts by — a number and
    a name, not a JSON path.

    `outcome` narrows the table: one of F9's five values, or `none` for the analyses
    where nothing has come back yet (F.1).
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
                # F9's other columns. Each is absent on an analysis stored before the
                # field existed, and renders as "—" rather than a zero or a guess:
                # sub-scores as integers 0–100, both scans as a verdict, the prompt
                # versions as written, and the cost as recorded.
                "sub_scores": _sub_scores(score),
                "readability": _readability_scan(application.scan_readability),
                "boolean": _boolean_scan(application.scan_boolean),
                "prompt_versions": dict(application.prompt_versions or {}),
                "token_cost_usd": application.token_cost_usd,
            }
        )

    if outcome == "none":
        rows = [row for row in rows if row["outcome"] in NO_OUTCOME]
    elif outcome in OUTCOMES:
        rows = [row for row in rows if row["outcome"] == outcome]

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


def _naive(value: datetime | None) -> datetime | None:
    """A datetime comparable across drivers: sqlite hands back naive rows (F.1)."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _stale_cutoff(days: int, today: datetime | None) -> datetime:
    reference = today or datetime.now(UTC)
    return _naive(reference) - timedelta(days=days)


def stale_application_count(
    profile_id: uuid.UUID,
    session: Session,
    *,
    days: int = STALE_DAYS,
    today: datetime | None = None,
) -> int:
    """Analyses older than `days` where nothing has come back yet (F.1's nudge).

    Owner-scoped like every other read: another profile's rows are not in the query at
    all, so the count cannot leak a stranger's job hunt.
    """
    cutoff = _stale_cutoff(days, today)
    count = 0
    for application in owned_rows(Application, session, profile_id):
        if application.outcome not in NO_OUTCOME:
            continue
        created = _naive(application.created_at)
        if created is None or created < cutoff:
            count += 1
    return count


def _owned_letter_template_id(
    profile_id: uuid.UUID, session: Session, template_id: str | uuid.UUID | None
) -> uuid.UUID | None:
    """The template link only if this profile owns the template (F1)."""
    if template_id is None or str(template_id).strip() == "":
        return None
    template = get_letter(profile_id, session, template_id)
    return template.id if template is not None else None


def save_application_letter(
    profile_id: uuid.UUID,
    session: Session,
    application_id: str | uuid.UUID,
    *,
    text: str,
    template_id: str | uuid.UUID | None,
) -> Application | None:
    """Store the letter that was sent (PRD F8, N8.4).

    The text is a snapshot: deleting the template it was built from cannot change it,
    and `letter_template_id` records which one it was (NULL when that template is not
    this profile's).
    """
    application = get_application(profile_id, session, application_id)
    if application is None:
        return None
    owned_template = _owned_letter_template_id(profile_id, session, template_id)
    application.letter_text = text.strip() or None
    application.letter_template_id = owned_template
    session.flush()
    return application
