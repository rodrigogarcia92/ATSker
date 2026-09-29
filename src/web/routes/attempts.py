"""Application attempts over HTTP (PRD F10.3, Run B): upload a file and test it.

The upload runs the whole attempt inside the POST (A5): a `running` row is committed
first, the pipeline runs, then the row is `done` or `failed`. The response is the
status partial, which is also what `GET …/attempts/{n}` returns for polling.
"""

import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from src.analysis import ceiling_for_report
from src.applications import get_application
from src.attempt_flags import discard_attempt
from src.attempt_merge import (
    apply_attempt_merge,
    apply_destination,
    attempt_draft,
    merge_plan,
)
from src.attempt_readiness import cap_target, readiness
from src.attempts import (
    MAX_ATTEMPTS,
    attempt_view,
    counted_attempts,
    create_attempt,
    extract,
    fail_attempt,
    finish_run,
    get_attempt,
    list_attempts,
    run_pipeline,
)
from src.bullets import list_bullets
from src.extract.client import (
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
)
from src.extract.resume import EmptyExtraction
from src.i18n import t
from src.ingest.documents import SUPPORTED_SUFFIXES, UnreadableDocument
from src.parse.gate import checks_not_run
from src.tracks import get_track, list_tracks
from src.web.alerts import ceiling_remainder
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import finding_rows
from src.web.recall import query_rows
from src.web.routes.ingest import MAX_UPLOAD_BYTES
from src.web.templating import render

router = APIRouter()

logger = logging.getLogger(__name__)


def failure_message(failure: Exception, lang: str) -> str:
    """What to say when an attempt's extraction produced nothing (F2.3.1)."""
    if isinstance(failure, EmptyExtraction):
        return t("import.empty_extraction", lang, characters=failure.characters)
    if isinstance(failure, UnreadableDocument):
        return t("import.unreadable", lang)
    return t("import.failed", lang)


def _analysis_score(application) -> int | None:
    score = (application.report or {}).get("score") or {}
    return score.get("capped")


def _previous_number(session, application, attempt) -> int | None:
    """The attempt the delta is measured against (C.0 answer 4): the previous one, or
    None for Intento 1, which is measured against the posting analysis."""
    rows = [
        row
        for row in list_attempts(application.profile_id, session, application.id)
        if row.attempt_no < attempt.attempt_no and row.status == "done"
    ]
    return rows[-1].attempt_no if rows else None


def _readiness(application, attempt):
    """F10.6's checklist for the attempt's report, or None while it has none."""
    if not attempt.report:
        return None
    return readiness(attempt.report, target=application.target_match)


def _status(request: Request, user, application, attempt, session):
    return render(
        request,
        "attempts/status.html",
        user=user,
        application=application,
        attempt=attempt,
        view=attempt_view(
            attempt,
            analysis_score=_analysis_score(application),
            previous=_previous_number(session, application, attempt),
        ),
        readiness=_readiness(application, attempt),
        attempts=list_attempts(application.profile_id, session, application.id),
    )


def _run_attempt(
    profile_id,
    session: Session,
    *,
    application,
    attempt,
    filename: str,
    data: bytes,
    display_name: str | None,
    lang: str,
) -> None:
    """Extract and score, with every failure landing on the row.

    A run that raises must never leave the row `running`: it would count towards the
    limit and read as failed only after ten minutes (A5). An unexpected exception is
    logged without the document's text and reported as a plain failure.
    """
    try:
        result = extract(
            profile_id,
            session,
            filename=filename,
            data=data,
            display_name=display_name,
            language_hint=lang,
        )
        report, analysis = run_pipeline(
            profile_id,
            session,
            application=application,
            attempt=attempt,
            extracted=result,
        )
        finish_run(attempt, report=report, analysis=analysis, lang=result.draft.language)
    except NoModelConfigured:
        fail_attempt(attempt, t("import.no_model", lang))
    except (
        ProviderUnavailable,
        StructuredOutputError,
        EmptyExtraction,
        UnreadableDocument,
    ) as failure:
        # A failure is not counted towards the limit (A6): `effective_status` and
        # `counted_attempts` both leave it out.
        fail_attempt(attempt, failure_message(failure, lang))
    except Exception:  # noqa: BLE001 - the row must not be left running
        logger.exception("attempt %s failed", attempt.id)  # never the document text
        fail_attempt(attempt, t("import.failed", lang))
    session.commit()


@router.post("/applications/{application_id}/attempts")
def attempt_upload(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    file: Annotated[UploadFile, File()],
):
    """Sync on purpose: FastAPI runs a `def` handler in the threadpool, so a run of
    30-90 s cannot freeze the event loop every other request on the instance shares.
    `file.file` is the synchronous read; nothing here awaits.
    """
    # Another profile's analysis is not found, not forbidden (F1).
    application = get_application(profile.id, session, application_id)
    if application is None:
        raise HTTPException(status_code=404)

    filename = (file.filename or "documento").strip()
    data = file.file.read()
    suffix = Path(filename).suffix.lower()
    # Preconditions: an empty, oversized or unsupported file never becomes an attempt,
    # so it cannot consume one of the ten.
    if not data:
        raise HTTPException(status_code=400, detail=t("import.no_file", user.ui_lang))
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=t("import.too_large", user.ui_lang))
    if suffix not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail=t("import.unsupported", user.ui_lang))
    if counted_attempts(profile.id, session, application.id) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=409,
            detail=t("attempt.limit", user.ui_lang, max=MAX_ATTEMPTS),
        )

    attempt = create_attempt(
        profile.id,
        session,
        application=application,
        filename=filename,
        data=data,
        file_format=suffix.lstrip("."),
    )
    # A5 step 1: the row exists as `running` before the work starts.
    session.commit()
    _run_attempt(
        profile.id,
        session,
        application=application,
        attempt=attempt,
        filename=filename,
        data=data,
        display_name=profile.display_name,
        lang=user.ui_lang,
    )
    return _status(request, user, application, attempt, session)


def _owned(profile_id, session, application_id: str, attempt_id: str):
    """`(application, attempt)` for this profile, or `(None, None)` for a 404.

    The attempt must also belong to the application in the path: an id from one
    analysis must not reach another's attempt, even inside the same profile (F1).
    """
    application = get_application(profile_id, session, application_id)
    if application is None:
        return None, None
    attempt = get_attempt(profile_id, session, attempt_id)
    if attempt is None or attempt.application_id != application.id:
        return None, None
    return application, attempt


@router.post("/applications/{application_id}/target")
def application_target(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    target: Annotated[str, Form()] = "",
    attempt: Annotated[str | None, Form()] = None,
):
    """Set the user's own stopping point for this posting (F10.6).

    Stored on the application (migration 0015) and capped at the ceiling's high end: a
    target above what the material allows is not attainable. An empty field clears it.
    """
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    ceiling = (application.report or {}).get("ceiling") or {}
    wanted = int(target) if target.strip().isdigit() else None
    application.target_match = cap_target(wanted, ceiling.get("high"))
    session.commit()
    if attempt:
        return RedirectResponse(
            f"/applications/{application_id}/attempts/{attempt}/report", status_code=303
        )
    return RedirectResponse(f"/applications/{application_id}", status_code=303)


@router.post("/applications/{application_id}/attempts/{attempt_id}/sent")
def attempt_sent(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
):
    """Mark this attempt as the version sent (F10.7).

    One switch at a time: every other attempt is cleared first and flushed, so the
    partial unique index never sees two sent rows in one transaction.
    """
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None:
        return render(request, "not_found.html", user=user, status_code=404)
    for row in list_attempts(profile.id, session, application.id):
        row.is_sent = False
    session.flush()
    attempt.is_sent = True
    application.sent_attempt_id = attempt.id
    session.commit()
    return _status(request, user, application, attempt, session)


@router.get("/applications/{application_id}/attempts/{attempt_id}/incorporate")
def attempt_incorporate(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
):
    """The F2.5 review for the attempt's new material — before anything is written."""
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None or not attempt.report:
        return render(request, "not_found.html", user=user, status_code=404)
    draft = attempt_draft(attempt.report)
    return render(
        request,
        "attempts/incorporate.html",
        user=user,
        application=application,
        attempt=attempt,
        plan=merge_plan(profile.id, session, draft),
        tracks=list_tracks(profile.id, session, active_only=True),
    )


@router.post("/applications/{application_id}/attempts/{attempt_id}/incorporate")
def attempt_incorporate_apply(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
    destination: Annotated[str, Form()] = "solo",
    track_id: Annotated[str | None, Form()] = None,
    new_name: Annotated[str | None, Form()] = None,
):
    """Apply the confirmed review, then the destination the user chose (F10.7)."""
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None or not attempt.report:
        return render(request, "not_found.html", user=user, status_code=404)
    draft = attempt_draft(attempt.report)
    plan = merge_plan(profile.id, session, draft)
    merged = apply_attempt_merge(profile.id, session, draft=draft, plan=plan)
    chosen = apply_destination(
        profile.id,
        session,
        application=application,
        bullet_ids=list(merged["bullet_ids"]),
        choice=destination,
        track_id=track_id,
        new_name=new_name,
    )
    session.commit()
    return render(
        request,
        "attempts/incorporated.html",
        user=user,
        application=application,
        attempt=attempt,
        counts=merged["counts"],
        destination=destination if chosen is not None else "solo",
    )


@router.get("/applications/{application_id}/attempts/{attempt_id}")
def attempt_status(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
):
    """The status partial the modal polls; a stale `running` row reads as failed."""
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _status(request, user, application, attempt, session)


@router.post("/applications/{application_id}/attempts/{attempt_id}/discard")
def attempt_discard(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
):
    """Drop the draft; the report and its flags stay (F10.7)."""
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None:
        return render(request, "not_found.html", user=user, status_code=404)
    discard_attempt(attempt)
    session.commit()
    return _status(request, user, application, attempt, session)


@router.get("/applications/{application_id}/attempts/{attempt_id}/report")
def attempt_report(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    attempt_id: str,
):
    """The full F5 report for the attempt, through the analysis's own template."""
    application, attempt = _owned(profile.id, session, application_id, attempt_id)
    if attempt is None or not attempt.report:
        return render(request, "not_found.html", user=user, status_code=404)
    report = dict(attempt.report)
    track = (
        get_track(profile.id, session, application.track_id)
        if application.track_id
        else None
    )
    stored_ceiling = report.get("ceiling")
    current_ceiling = ceiling_for_report(profile.id, session, report=report, track=track)
    same = bool(
        stored_ceiling
        and current_ceiling
        and stored_ceiling.get("fingerprint") == current_ceiling.get("fingerprint")
    )
    ceiling = stored_ceiling if same else current_ceiling
    kind = attempt.file_format or ""
    return render(
        request,
        "analyze/report.html",
        user=user,
        profile=profile,
        # The attempt's own run metadata, in the shape the report template reads.
        application=SimpleNamespace(
            id=application.id,
            title=application.title,
            company=application.company,
            track_id=application.track_id,
            created_at=attempt.created_at,
            weights_version=attempt.weights_version,
            prompt_versions=attempt.prompt_versions or {},
            token_cost_usd=attempt.token_cost_usd,
            jd_hash=application.jd_hash,
            scan_readability=report.get("gate"),
            scan_boolean=report.get("recall"),
        ),
        report=report,
        ceiling=ceiling,
        ceiling_recomputed=ceiling is not None and not same,
        ceiling_remainder=ceiling_remainder(ceiling, user.ui_lang) if ceiling else None,
        # C.0 answer 2: an attempt's full report is read-only.
        attempt_view=True,
        attempt_no=attempt.attempt_no,
        readiness=_readiness(application, attempt),
        advice_for_file=True,
        findings=finding_rows(report.get("gate") or {}, user.ui_lang),
        live_bullets={
            str(bullet.id) for bullet in list_bullets(profile.id, session, active_only=True)
        },
        # An attempt has no source résumé: the findings belong to the uploaded file.
        findings_resume=None,
        findings_kind=kind,
        recall={"rows": query_rows(report.get("recall") or {}, user.ui_lang)},
        not_run=checks_not_run(kind),
    )
