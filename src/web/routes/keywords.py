"""Probable keywords over HTTP (PRD F7.5, §12.5): the pop-up, the page behind it, the call.

Opening is free: the two GETs render what would be sent and a button, and never call the
provider. The paid call is the POST, once per press and cached by content hash, so asking
again for the same material costs nothing. Nothing here writes — the answer is a list of
suggestions the user applies to their own file — and everything is scoped to the signed-in
profile: another profile's application or attempt is a 404.

An attempt's own report has its own Keywords sub-score, so the same routes take `?attempt=`
and word everything for the uploaded file.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request

from src.applications import get_application
from src.attempts import get_attempt
from src.extract.client import model_configured
from src.generate.keywords import (
    Prepared,
    describe,
    prepare_inference,
    run_inference,
)
from src.tracks import get_track
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.generation_errors import KEYWORDS, PROVIDER_ERRORS, failed, no_model
from src.web.templating import render

router = APIRouter()


def _target(profile, session, application_id: str, attempt_id: str | None):
    """`(application, report, track, attempt)`, or `None` for a 404.

    With an attempt the report is the uploaded file's own, and the attempt must belong to
    this application, as everywhere else (F1).
    """
    application = get_application(profile.id, session, application_id)
    if application is None:
        return None
    attempt = None
    report = application.report or {}
    if attempt_id:
        attempt = get_attempt(profile.id, session, attempt_id)
        if attempt is None or attempt.application_id != application.id or not attempt.report:
            return None
        report = attempt.report
    track = get_track(profile.id, session, application.track_id) if application.track_id else None
    return application, report, track, attempt


def _page(
    request: Request,
    user,
    profile,
    session,
    target,
    *,
    dialog: bool,
    prepared: Prepared | None,
    items: list | None = None,
    dropped: int = 0,
    error: str | None = None,
    retry: bool = False,
):
    application, report, _track, attempt = target
    suffix = f"?attempt={attempt.id}" if attempt is not None else ""
    return render(
        request,
        "generate/_keywords_body.html" if dialog else "generate/keywords.html",
        user=user,
        profile=profile,
        application=application,
        attempt=attempt,
        # A file, not a track: an attempt, or an analysis of a stored CV (F11.4).
        for_file=attempt is not None or bool(report.get("cv")),
        dialog=dialog,
        remaining=len(prepared.candidates) if prepared is not None else 0,
        items=items,
        dropped=dropped,
        error=error,
        # The call costs money, so it is a button on a POST, never a GET (F.0). After a
        # failure it comes back, except when no model is configured.
        run_url=(
            f"/applications/{application.id}/keywords/infer"
            if prepared is not None and items is None and (error is None or retry)
            else None
        ),
        back_url=f"/applications/{application.id}"
        + (f"/attempts/{attempt.id}/report" if attempt is not None else ""),
        page_url=f"/applications/{application.id}/keywords{suffix}",
    )


def _open(request, user, profile, session, application_id, attempt_id, *, dialog: bool):
    target = _target(profile, session, application_id, attempt_id)
    if target is None:
        return render(request, "not_found.html", user=user, status_code=404)
    _application, report, track, attempt = target
    prepared = prepare_inference(
        profile.id,
        session,
        report=report,
        track=track,
        for_file=attempt is not None or bool(report.get("cv")),
    )
    error = None
    if prepared is not None and not model_configured():
        error = no_model(KEYWORDS, user.ui_lang)
    return _page(
        request, user, profile, session, target, dialog=dialog, prepared=prepared, error=error
    )


@router.get("/applications/{application_id}/keywords")
def keywords_page(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    attempt: str | None = None,
):
    """The no-JavaScript path to the pop-up's flow. A GET: no provider call."""
    return _open(request, user, profile, session, application_id, attempt, dialog=False)


@router.get("/applications/{application_id}/keywords/dialog")
def keywords_dialog(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    attempt: str | None = None,
):
    """The pop-up's partial: how many keywords are left and a button. No provider call."""
    return _open(request, user, profile, session, application_id, attempt, dialog=True)


@router.post("/applications/{application_id}/keywords/infer")
def keywords_infer(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    dialog: Annotated[str | None, Form()] = None,
    attempt: Annotated[str | None, Form()] = None,
):
    """One paid call, on demand: the probable keywords (F7.5). Writes nothing."""
    target = _target(profile, session, application_id, attempt)
    if target is None:
        return render(request, "not_found.html", user=user, status_code=404)
    _application, report, track, attempt_row = target
    popup = dialog == "1"
    prepared = prepare_inference(
        profile.id,
        session,
        report=report,
        track=track,
        for_file=attempt_row is not None or bool(report.get("cv")),
    )
    if prepared is None:
        return _page(request, user, profile, session, target, dialog=popup, prepared=None)
    if not model_configured():
        return _page(
            request,
            user,
            profile,
            session,
            target,
            dialog=popup,
            prepared=prepared,
            error=no_model(KEYWORDS, user.ui_lang),
        )

    names = [profile.display_name] if profile.display_name else None
    # Everything the prompt reads was read above; the reads end before the call.
    session.commit()
    try:
        result = run_inference(session, prepared, profile_id=profile.id, known_names=names)
    except PROVIDER_ERRORS as exc:
        # A paid call that failed is still paid; keep the ledger and report plainly.
        session.commit()
        return _page(
            request,
            user,
            profile,
            session,
            target,
            dialog=popup,
            prepared=prepared,
            error=failed(exc, KEYWORDS, user.ui_lang),
            retry=True,
        )
    session.commit()
    return _page(
        request,
        user,
        profile,
        session,
        target,
        dialog=popup,
        prepared=prepared,
        items=describe(result.items, prepared),
        dropped=result.dropped,
    )
