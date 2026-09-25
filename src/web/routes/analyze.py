"""The analysis page: paste a posting, get the report it produces (PRD F4/F8).

One route runs the pipeline and one renders what was stored, so the report the
user reads is the row the dataset keeps — not a re-render of live data that could
drift from it.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.analysis import analyze
from src.applications import create_application, get_application
from src.bullets import list_bullets
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.grading import CitationViolation
from src.i18n import t
from src.parse.gate import checks_not_run
from src.resumes import source_document_for_track
from src.tracks import get_track, list_tracks
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import document_kind, finding_rows
from src.web.recall import query_rows
from src.web.templating import render

router = APIRouter()

EMPTY_FORM = {"jd_text": "", "company": "", "title": "", "track_id": ""}


def _form(
    request: Request,
    user,
    session,
    profile,
    *,
    values: dict | None = None,
    error: str | None = None,
):
    return render(
        request,
        "analyze/form.html",
        user=user,
        profile=profile,
        values=values or EMPTY_FORM,
        active_bullets=len(list_bullets(profile.id, session, active_only=True)),
        tracks=list_tracks(profile.id, session, active_only=True),
        can_analyze=model_configured(),
        error=error,
    )


@router.get("/analyze")
def analyze_form(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return _form(request, user, session, profile)


@router.post("/analyze")
def analyze_submit(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    jd_text: Annotated[str, Form()],
    company: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    track_id: Annotated[str | None, Form()] = None,
):
    values = {
        "jd_text": jd_text,
        "company": company or "",
        "title": title or "",
        "track_id": track_id or "",
    }
    if not jd_text.strip():
        message = t("analyze.need_text", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)

    track = None
    if track_id:
        # An id from a form is as untrusted as one from a URL: not ours is not found,
        # and an analysis silently scored against every bullet instead of the chosen
        # track would be a wrong answer, not a degraded one.
        track = get_track(profile.id, session, track_id)
        if track is None:
            raise HTTPException(status_code=404)

    try:
        # F2.8: the ledger rows of every call this analysis makes record whose call
        # they were — attribution rides `options`, which `analyze` forwards unchanged.
        analysis = analyze(
            profile.id,
            session,
            jd_text=jd_text,
            company=company,
            title=title,
            track=track,
            options=CallOptions(profile_id=profile.id),
        )
    except NoModelConfigured:
        message = t("analyze.no_model", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    except (ProviderUnavailable, StructuredOutputError, CitationViolation):
        # The calls that did succeed were paid for and are valid cache entries, so
        # the ledger keeps them even though no application was produced.
        session.commit()
        message = t("analyze.failed", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)

    application = create_application(
        profile.id,
        session,
        jd_text=jd_text,
        jd_hash=analysis.jd_hash,
        company=analysis.company,
        title=analysis.title,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
        track_id=track.id if track is not None else None,
        # The findings of the document that capped the score, if one did (F5.1). The
        # report already carries the same JSON under `gate`; the column is what the
        # report page reads, and what N4's boolean recall will sit beside.
        scan_readability=analysis.report.get("gate"),
        # Scan B (F5.2): the queries and what they found, beside the score and never in
        # it. The report carries the same JSON for the snapshot the page renders.
        scan_boolean=analysis.report.get("recall"),
    )
    session.commit()
    return RedirectResponse(f"/applications/{application.id}", status_code=303)


@router.get("/applications/{application_id}")
def application_report(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    # The readability panel names the checks the file's format could not answer, so it
    # needs the source document's kind — the résumé the track was built from.
    source = (
        source_document_for_track(profile.id, session, application.track_id)
        if application.track_id
        else None
    )
    return render(
        request,
        "analyze/report.html",
        user=user,
        profile=profile,
        application=application,
        report=application.report,
        findings=finding_rows(application.scan_readability or {}, user.ui_lang),
        recall={"rows": query_rows(application.scan_boolean or {}, user.ui_lang)},
        not_run=(
            checks_not_run(document_kind(source.filename))
            if source is not None and application.scan_readability
            else ()
        ),
    )
