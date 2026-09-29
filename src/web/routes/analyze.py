"""The analysis page: paste a posting, get the report it produces (PRD F4/F8).

One route runs the pipeline and one renders what was stored, so the report the
user reads is the row the dataset keeps — not a re-render of live data that could
drift from it.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.analysis import analyze, ceiling_for_report
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
from src.recommend import recommend
from src.resumes import source_document_for_track
from src.tracks import get_track, list_tracks
from src.web.alerts import ceiling_remainder
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import document_kind, finding_rows
from src.web.forms import is_checked
from src.web.recall import query_rows
from src.web.templating import render

router = APIRouter()

# The form's own fields, without `recommend`: its default depends on the tracks the
# profile has, so it is decided in `_form` rather than frozen into an empty form.
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
    tracks = list_tracks(profile.id, session, active_only=True)
    # F7.1: a fresh form ticks "recommend a track" when there is a choice to make —
    # two or more active tracks. With one there is nothing to choose between, and with
    # none the analysis is the no-track one. A re-rendered form (a validation error)
    # keeps exactly what was submitted, ticked or not: the box is the user's, and the
    # default never overrides it. A form pre-filled from `?application=` has no box of
    # its own, so it takes the default.
    submitted = dict(values or EMPTY_FORM)
    submitted.setdefault("recommend", "on" if len(tracks) >= 2 else "off")
    return render(
        request,
        "analyze/form.html",
        user=user,
        profile=profile,
        values=submitted,
        active_bullets=len(list_bullets(profile.id, session, active_only=True)),
        tracks=tracks,
        can_analyze=model_configured(),
        error=error,
    )


@router.get("/analyze")
def analyze_form(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application: str | None = None,
):
    """The form, optionally pre-filled from a previous analysis (PRD §12.1 item 1).

    "Analizar con otro puesto" carries the posting, the company and the title over so
    the same JD can be scored against a different track. The id is as untrusted as any
    other: owner-scoped, and another profile's is a 404, not a redirect.
    """
    values = None
    if application:
        previous = get_application(profile.id, session, application)
        if previous is None:
            return render(request, "not_found.html", user=user, status_code=404)
        values = {
            "jd_text": previous.jd_text or "",
            "company": previous.company or "",
            "title": previous.title or "",
        }
    return _form(request, user, session, profile, values=values)


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
    # The box is named `recommend` in the form; the parameter is not, so that the
    # imported function of the same name stays the function (F7.1).
    recommend_track: Annotated[str | None, Form(alias="recommend")] = None,
):
    values = {
        "jd_text": jd_text,
        "company": company or "",
        "title": title or "",
        "track_id": track_id or "",
        "recommend": "on" if is_checked(recommend_track) else "off",
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
        if track is None and is_checked(recommend_track):
            # F7.1: no track chosen and the box ticked — score every candidate track
            # and store the winner. The report carries the whole table.
            analysis = recommend(
                profile.id,
                session,
                jd_text=jd_text,
                company=company,
                title=title,
                options=CallOptions(profile_id=profile.id),
            )
        else:
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

    # F7.1: a recommendation stores the winner's track — that is the application the
    # user would send — and the report names it either way. The snapshot holds the id
    # as a string, which is what a JSON report can hold.
    stored_track = (analysis.report.get("track") or {}).get("id")
    try:
        winner_track_id = uuid.UUID(str(stored_track)) if stored_track else None
    except ValueError:  # pragma: no cover - only a hand-edited report can do this
        winner_track_id = None
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
        track_id=track.id if track is not None else winner_track_id,
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
    # F10.2/A10: show the ceiling the analysis stored, and recompute it only when the
    # master data it reads has moved since — the recomputation is offline, and a stored
    # ceiling whose fingerprint still matches is shown as it was, not re-derived.
    track = (
        get_track(profile.id, session, application.track_id)
        if application.track_id
        else None
    )
    stored_ceiling = application.report.get("ceiling")
    current_ceiling = ceiling_for_report(
        profile.id, session, report=application.report, track=track
    )
    same = bool(
        stored_ceiling
        and current_ceiling
        and stored_ceiling.get("fingerprint") == current_ceiling.get("fingerprint")
    )
    ceiling = stored_ceiling if same else current_ceiling
    return render(
        request,
        "analyze/report.html",
        user=user,
        profile=profile,
        application=application,
        report=application.report,
        ceiling=ceiling,
        ceiling_recomputed=ceiling is not None and not same,
        ceiling_remainder=ceiling_remainder(ceiling, user.ui_lang) if ceiling else None,
        findings=finding_rows(application.scan_readability or {}, user.ui_lang),
        # F7.3 Tier 3a: the rephrase control links only to a bullet that still exists
        # and is active — a stored report renders a deleted citation from its snapshot,
        # without a link to the row that is gone (F2.8/F5.4).
        live_bullets={
            str(bullet.id) for bullet in list_bullets(profile.id, session, active_only=True)
        },
        # F5.1.1: the report links "show me where" through the track's source résumé —
        # the document whose gate capped this score — and only when there is one.
        findings_resume=source,
        findings_kind=document_kind(source.filename) if source is not None else "",
        recall={"rows": query_rows(application.scan_boolean or {}, user.ui_lang)},
        not_run=(
            checks_not_run(document_kind(source.filename))
            if source is not None and application.scan_readability
            else ()
        ),
    )
