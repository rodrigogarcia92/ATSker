"""What K2 would do to the reports already stored (PRD F5.5.3).

Stored reports were scored with K1 (BM25 over every term the posting asks for). This
script recomputes the Keywords sub-score with K2 — the terms a recruiter would type,
all of a term's words in one unit — over the same document the report was scored on,
and prints what moved. It answers one question before `w5` ships: how many stored
reports move, and by how much.

    uv run python scripts/keyword_replay.py
    uv run python scripts/keyword_replay.py --since 7d
    uv run python scripts/keyword_replay.py --detail <application id>

Read-only: it opens the database the app uses (`DATABASE_URL`, as `latency_report.py`
does), reads `applications.report`, rebuilds the document from the track or the CV the
report names — as `ceiling_for_report` does — and prints. Nothing is written. A report
with no Keywords sub-score, no readable posting or no rebuildable document is counted
as skipped, never guessed at.

K1 is the value the report stored, not a recomputation: the point is what the stored
number was, against what the new rule would say over the same material. Job Match with
K2 is the stored total plus the Keywords weight times the change; a report stored under
`w5` already holds K2 and reads as no change.
"""

import argparse
import statistics
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from scripts.llm_costs import parse_since  # noqa: E402
from src.cv_context import cv_document  # noqa: E402
from src.db import session_scope  # noqa: E402
from src.documents import DocumentUnit, track_document  # noqa: E402
from src.jd import StructuredJD  # noqa: E402
from src.models import Application, Track  # noqa: E402
from src.score.aggregate import SubScore  # noqa: E402
from src.score.keywords import keyword_context  # noqa: E402
from src.score.weights import W5  # noqa: E402
from src.tracks import get_track  # noqa: E402
from src.vocabulary import alias_map  # noqa: E402

DEFAULT_SINCE = "30d"
TITLE_WIDTH = 40


def _score(report: Mapping[str, object]) -> Mapping[str, object]:
    score = report.get("score")
    return score if isinstance(score, Mapping) else {}


def _stored_k1(report: Mapping[str, object]) -> float | None:
    """The Keywords value the report stored, which `w4` computed with K1."""
    sub_scores = _score(report).get("sub_scores")
    if not isinstance(sub_scores, Mapping):
        return None
    keywords = sub_scores.get("keywords")
    if not isinstance(keywords, Mapping):
        return None
    value = keywords.get("value")
    return float(value) if isinstance(value, (int, float)) else None


def _job_match(report: Mapping[str, object]) -> float | None:
    capped = _score(report).get("capped")
    return float(capped) if isinstance(capped, (int, float)) else None


def _track(application: Application, session) -> Track | None:
    """The track the report names (F12.4's snapshot), else the application's own."""
    report = application.report or {}
    snapshot = report.get("track")
    named = snapshot.get("id") if isinstance(snapshot, Mapping) else None
    track_id = named or application.track_id
    if not track_id:
        return None
    return get_track(application.profile_id, session, str(track_id))


def _document(
    application: Application, session, jd: StructuredJD
) -> list[DocumentUnit] | None:
    """The document the report was scored on, rebuilt now; None when it cannot be."""
    report = application.report or {}
    track = _track(application, session)
    if report.get("cv") is not None:
        rebuilt = cv_document(
            application.profile_id, session, report=report, track=track, lang=jd.language
        )
        return rebuilt[0] if rebuilt is not None else None
    return track_document(application.profile_id, session, track, jd.language)


def _k2(application: Application, session, jd: StructuredJD) -> SubScore | None:
    document = _document(application, session, jd)
    if document is None:
        return None
    return keyword_context(
        jd, [unit.text for unit in document], aliases=alias_map(session)
    )


def _line(
    application: Application, k1: float, k2: SubScore, job_match: float | None
) -> str:
    report = application.report or {}
    jd = report.get("jd")
    title = str(jd.get("title") or "")[:TITLE_WIDTH] if isinstance(jd, Mapping) else ""
    change = k2.value - k1
    moved = (
        "–"
        if job_match is None
        else f"{job_match:.1f} → {job_match + 100 * W5.keywords * change:.1f}"
    )
    kept = int(k2.detail.get("terms") or 0)
    dropped = len(k2.detail.get("dropped") or [])
    created = application.created_at.date().isoformat() if application.created_at else ""
    return (
        f"{created}  {title:<{TITLE_WIDTH}}  K1 {k1:.3f}  K2 {k2.value:.3f}  "
        f"{change:+.3f}  JM {moved}  terms {kept} kept/{dropped} dropped"
    )


def cmd_report(since_raw: str) -> int:
    """One line per replayable report, then the distribution of the K2 − K1 change."""
    since = parse_since(since_raw)
    lines: list[str] = []
    changes: list[float] = []
    skipped = 0
    with session_scope() as session:
        rows = list(
            session.scalars(
                select(Application)
                .where(Application.created_at >= since)
                .order_by(Application.created_at, Application.id)
            )
        )
        for application in rows:
            report = application.report or {}
            jd_dict = report.get("jd")
            k1 = _stored_k1(report)
            if k1 is None or not isinstance(jd_dict, Mapping):
                skipped += 1
                continue
            jd = StructuredJD(**jd_dict)
            k2 = _k2(application, session, jd)
            if k2 is None:
                skipped += 1
                continue
            lines.append(_line(application, k1, k2, _job_match(report)))
            changes.append(round(k2.value - k1, 4))

    for line in lines:
        print(line)
    print(f"skipped (no keywords sub-score or document): {skipped}")
    if changes:
        print(
            f"reports: {len(changes)}   median change {statistics.median(changes):+.3f}   "
            f"range {min(changes):+.3f} .. {max(changes):+.3f}"
        )
    else:
        print("reports: 0")
    return 0


def _names(values: Sequence[str]) -> str:
    return ", ".join(values) if values else "(none)"


def cmd_detail(application_id: str) -> int:
    """The K2 lists of one report: what it matches, what it misses, what it drops."""
    try:
        key = uuid.UUID(application_id)
    except ValueError:
        print(f"no application {application_id}")
        return 1
    with session_scope() as session:
        rows = session.scalars(select(Application).where(Application.id == key)).all()
        if not rows:
            print(f"no application {application_id}")
            return 1
        application = rows[0]
        report = application.report or {}
        jd_dict = report.get("jd")
        k1 = _stored_k1(report)
        if k1 is None or not isinstance(jd_dict, Mapping):
            print(f"application {application_id} has no Keywords sub-score or posting")
            return 1
        jd = StructuredJD(**jd_dict)
        k2 = _k2(application, session, jd)
        if k2 is None:
            print(f"application {application_id} has no document to rebuild")
            return 1

    print(f"{application_id}  {jd.title}")
    print(f"K1 {k1:.3f}  K2 {k2.value:.3f}  {k2.value - k1:+.3f}")
    print(f"matched: {_names(k2.matched)}")
    print(f"missing: {_names(k2.missing)}")
    print(f"dropped: {_names([str(item) for item in k2.detail.get('dropped') or []])}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the stored reports under K2: the Keywords value each one would have, "
            "the Job Match it would move, and the change's median and range. Read-only."
        )
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"ISO date or timestamp, or a window (2d, 48h); default {DEFAULT_SINCE}",
    )
    parser.add_argument(
        "--detail",
        default=None,
        metavar="APPLICATION_ID",
        help="print the K2 matched, missing and dropped lists of one report",
    )
    args = parser.parse_args(argv)
    if args.detail is not None:
        return cmd_detail(args.detail)
    return cmd_report(args.since)


if __name__ == "__main__":
    raise SystemExit(main())
