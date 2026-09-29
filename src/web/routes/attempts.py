"""Application attempts over HTTP (PRD F10.3, Run B): upload a file and test it.

The upload runs the whole attempt inside the POST (A5): a `running` row is committed
first, the pipeline runs, then the row is `done` or `failed`. The response is the
status partial, which is also what `GET …/attempts/{n}` returns for polling.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from src.applications import get_application
from src.attempts import (
    MAX_ATTEMPTS,
    counted_attempts,
    create_attempt,
    effective_status,
    extract,
    fail_attempt,
    finish_run,
    list_attempts,
    run_pipeline,
)
from src.extract.client import (
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
)
from src.extract.resume import EmptyExtraction
from src.i18n import t
from src.ingest.documents import SUPPORTED_SUFFIXES, UnreadableDocument
from src.web.deps import DbSession, OwnProfile, SignedInUser
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
