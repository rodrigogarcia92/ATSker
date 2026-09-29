"""Application attempts (PRD F10.3, A5/A6): test an edited CV against an analysis.

An attempt is a file the user will send, scored against the posting an application
already carries. It is **not** stored as master data: the bytes are read into memory,
hashed first, and never written to disk, a temp file or the database (A5). What
survives is the report, the SHA-256 and the draft, and the draft only until the user
discards it.

The run happens inside the POST (A5): a `running` row is committed before the work
starts, then the pipeline runs, then the row is marked `done` or `failed` with `error`
set. Cloud Run throttles CPU after a response, so there is no background worker to
hand it to. `effective_status` reads a `running` row older than ten minutes as failed,
because nothing will ever finish it.

The extraction reuses ingest (A6): the same call, the same F2.3.1 guards — an empty
extraction is retried once and then fails plainly, a failure is not counted towards
the limit, and a failure is never cached.
"""

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analysis import preparation_from_report, queries_from_report, score_track
from src.attempt_track import ephemeral_track
from src.extract.client import CallOptions, Completion
from src.extract.resume import ResumeExtraction, extract_resume
from src.ingest.documents import LoadedDocument, load_document
from src.ingest.draft import ResumeDraft, build_draft
from src.models import Application, ApplicationAttempt
from src.parse.gate import ParseReport
from src.tracks import get_track

# F10.3/A5: at most ten attempts per application, and a run older than this reads as
# failed however it was left.
MAX_ATTEMPTS = 10
STALE_AFTER = timedelta(minutes=10)

# What the limit counts: a running or finished attempt. A failed one — an empty
# extraction, an unreadable file — is not counted (A6), so a failure cannot consume
# the user's budget.
COUNTED_STATUSES = ("running", "done")


def now() -> datetime:
    return datetime.now(UTC)


def counted_attempts(
    profile_id: uuid.UUID, session: Session, application_id: uuid.UUID
) -> int:
    """The attempts of this application that count towards the limit."""
    stmt = select(func.count()).select_from(ApplicationAttempt).where(
        ApplicationAttempt.profile_id == profile_id,
        ApplicationAttempt.application_id == application_id,
        ApplicationAttempt.status.in_(COUNTED_STATUSES),
    )
    return int(session.scalar(stmt) or 0)


def list_attempts(
    profile_id: uuid.UUID, session: Session, application_id: uuid.UUID
) -> list[ApplicationAttempt]:
    stmt = (
        select(ApplicationAttempt)
        .where(
            ApplicationAttempt.profile_id == profile_id,
            ApplicationAttempt.application_id == application_id,
        )
        .order_by(ApplicationAttempt.attempt_no)
    )
    return list(session.scalars(stmt))


def get_attempt(
    profile_id: uuid.UUID, session: Session, attempt_id: str | uuid.UUID
) -> ApplicationAttempt | None:
    from src.scoping import owned_row

    return owned_row(ApplicationAttempt, session, profile_id, attempt_id)


def _next_number(
    profile_id: uuid.UUID, session: Session, application_id: uuid.UUID
) -> int:
    stmt = select(func.max(ApplicationAttempt.attempt_no)).where(
        ApplicationAttempt.profile_id == profile_id,
        ApplicationAttempt.application_id == application_id,
    )
    return int(session.scalar(stmt) or 0) + 1


def create_attempt(
    profile_id: uuid.UUID,
    session: Session,
    *,
    application: Application,
    filename: str,
    data: bytes,
    file_format: str,
) -> ApplicationAttempt:
    """Commit the `running` row before any work starts (A5 step 1)."""
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=profile_id,
        attempt_no=_next_number(profile_id, session, application.id),
        file_sha256=hashlib.sha256(data).hexdigest(),
        file_format=file_format,
        status="running",
        prompt_versions={},
        # Written here rather than left to the column's server default: the ten-minute
        # staleness rule (A5) reads this value, and a row must say when it started.
        created_at=now(),
    )
    session.add(attempt)
    session.flush()
    return attempt


def fail_attempt(attempt: ApplicationAttempt, message: str) -> None:
    """Mark a run failed, with the plain message the modal shows (A5 step 3)."""
    attempt.status = "failed"
    attempt.error = message


def effective_status(attempt: ApplicationAttempt, *, at: datetime | None = None) -> str:
    """`running` older than ten minutes reads as failed (A5)."""
    if attempt.status != "running":
        return attempt.status
    started = attempt.created_at
    if started is None:
        return "running"
    if started.tzinfo is None:
        started = started.replace(tzinfo=UTC)
    return "failed" if (at or now()) - started > STALE_AFTER else "running"


@dataclass(frozen=True)
class Extraction:
    """What one attempt's extraction produced, before anything is scored."""

    loaded: LoadedDocument
    extraction: ResumeExtraction
    draft: ResumeDraft
    # The call itself, so the attempt's report names what was paid for (F10.3/A9).
    completion: Completion


def extract(
    profile_id: uuid.UUID,
    session: Session,
    *,
    filename: str,
    data: bytes,
    display_name: str | None,
    language_hint: str | None = None,
) -> Extraction:
    """Readability, then résumé extraction with the F2.3.1 guards (A6).

    `load_document` runs the F5.1 gate in the file format's subset; `extract_resume`
    retries an empty answer once and then raises `EmptyExtraction` rather than
    handing the review screen an empty draft.
    """
    loaded = load_document(filename, data)
    extraction, completion = extract_resume(
        session,
        loaded.text,
        known_names=[display_name] if display_name else None,
        options=CallOptions(profile_id=profile_id),
    )
    draft = build_draft(session, extraction, language_hint=language_hint)
    return Extraction(
        loaded=loaded, extraction=extraction, draft=draft, completion=completion
    )


def gate_of(loaded: LoadedDocument) -> ParseReport:
    return loaded.gate




def run_pipeline(
    profile_id: uuid.UUID,
    session: Session,
    *,
    application: Application,
    attempt: ApplicationAttempt,
    extracted: Extraction,
) -> tuple[dict, object]:
    """Score the file as an ephemeral track, reusing the analysis (F10.3/B.3).

    The posting (F10.3 step 1's "reused at no cost") and the recruiter's queries come
    from the stored report, so the only calls are the attempt's own: the extraction
    already made, and one grading call — which the content-hash cache answers without
    a provider call when the file's evidence is the analysis's own (A4).
    """
    track = (
        get_track(profile_id, session, application.track_id)
        if application.track_id
        else None
    )
    ephemeral = ephemeral_track(
        profile_id, session, application=application, draft=extracted.draft
    )
    prepared = preparation_from_report(
        application.report, session, extraction=extracted.completion
    )
    analysis = score_track(
        profile_id,
        session,
        jd_text=application.jd_text,
        prepared=prepared,
        gate=extracted.loaded.gate,
        track=track,
        queries=queries_from_report(application.report),
        bullets=list(ephemeral.bullets),
        document=list(ephemeral.document),
        options=CallOptions(profile_id=profile_id),
        interpret=False,
    )
    report = dict(analysis.report)
    # A6: the draft lives in the report, so "Incorporar a mi material" can open the
    # F2.5 review from an attempt; "Descartar" blanks it and keeps everything else.
    report["draft"] = extracted.draft.model_dump(mode="json")
    # The file's bullets as read: master ids for unchanged text, temporary ids with
    # their snapshot for new or changed text (F10.5 reads this).
    report["bullets"] = [snapshot.to_dict() for snapshot in ephemeral.snapshots]
    return report, analysis



def finish_run(
    attempt: ApplicationAttempt, *, report: dict, analysis, lang: str | None = None
) -> None:
    """Store the run's report and its headline numbers on the row (A5/A9)."""
    ceiling = report.get("ceiling") or {}
    score = report.get("score") or {}
    attempt.report = report
    attempt.lang = lang or attempt.lang
    attempt.job_match = score.get("capped")
    attempt.ceiling_low = ceiling.get("low")
    attempt.ceiling_high = ceiling.get("high")
    attempt.weights_version = str(score.get("weights_version") or "")
    attempt.vocabulary_hash = str(report.get("vocabulary_hash") or "")
    attempt.prompt_versions = dict(attempt.prompt_versions or {})
    attempt.token_cost_usd = analysis.cost_usd
    attempt.status = "done"
    attempt.error = None


def application_attempts_report(attempts: Sequence[ApplicationAttempt]) -> list[dict]:
    """`Intento N` rows for the attempts list, newest shape, for the partial."""
    return [
        {
            "id": str(attempt.id),
            "attempt_no": attempt.attempt_no,
            "status": effective_status(attempt),
            "job_match": attempt.job_match,
            "ceiling_low": attempt.ceiling_low,
            "ceiling_high": attempt.ceiling_high,
            "is_sent": attempt.is_sent,
            "error": attempt.error,
        }
        for attempt in attempts
    ]
