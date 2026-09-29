"""Application attempts over HTTP (PRD F10.3, Run B): upload a file and test it.

The upload runs the whole attempt inside the POST (A5): a `running` row is committed
first, the pipeline runs, then the row is `done` or `failed`. The response is the
status partial, which is also what `GET …/attempts/{n}` returns for polling.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from src.analysis import ceiling_for_report
from src.applications import get_application
from src.attempt_flags import discard_attempt
from src.attempts import (
    MAX_ATTEMPTS,
    counted_attempts,
    create_attempt,
    effective_status,
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
from src.tracks import get_track
from src.web.alerts import ceiling_remainder
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import finding_rows
from src.web.recall import query_rows
from src.web.routes.ingest import MAX_UPLOAD_BYTES
from src.web.templating import render

router = APIRouter()


def failure_message(failure: Exception, lang: str) -> str:
    """What to say when an attempt's extraction produced nothing (F2.3.1)."""
    if isinstance(failure, EmptyExtraction):
        return t("import.empty_extraction", lang, characters=failure.characters)
    if isinstance(failure, UnreadableDocument):
        return t("import.unreadable", lang)
    return t("import.failed", lang)


def _status(request: Request, user, application, attempt, session):
    return render(
        request,
        "attempts/status.html",
        user=user,
        application=application,
        attempt=attempt,
        status=effective_status(attempt),
        attempts=list_attempts(application.profile_id, session, application.id),
    )


@router.post("/applications/{application_id}/attempts")
async def attempt_upload(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application_id: str,
    file: Annotated[UploadFile, File()],
):
    # Another profile's analysis is not found, not forbidden (F1).
    application = get_application(profile.id, session, application_id)
    if application is None:
        raise HTTPException(status_code=404)

    filename = (file.filename or "documento").strip()
    data = await file.read()
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

    try:
        # The reads end here; `complete_json` refuses to run inside a transaction.
        result = extract(
            profile.id,
            session,
            filename=filename,
            data=data,
            display_name=profile.display_name,
            language_hint=user.ui_lang,
        )
    except NoModelConfigured:
        fail_attempt(attempt, t("import.no_model", user.ui_lang))
    except (
        ProviderUnavailable,
        StructuredOutputError,
        EmptyExtraction,
        UnreadableDocument,
    ) as failure:
        # A failure is not counted towards the limit (A6): `effective_status` and
        # `counted_attempts` both leave it out.
        fail_attempt(attempt, failure_message(failure, user.ui_lang))
    else:
        report, analysis = run_pipeline(
            profile.id,
            session,
            application=application,
            attempt=attempt,
            extracted=result,
        )
        finish_run(attempt, report=report, analysis=analysis, lang=result.draft.language)
    session.commit()
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
