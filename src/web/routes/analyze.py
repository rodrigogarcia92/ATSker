"""The analysis page: paste a posting, get the report it produces (PRD F4/F8).

One route runs the pipeline and one renders what was stored, so the report the
user reads is the row the dataset keeps — not a re-render of live data that could
drift from it.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.analysis import prepare, shown_ceiling
from src.applications import create_application, get_application
from src.attempts import application_attempts_report
from src.attempts import list_attempts as list_attempt_rows
from src.bullets import list_bullets
from src.cv_analysis import analyze_cv, rank_tracks
from src.cv_context import draft_digest
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.grading import CitationViolation
from src.generate.keywords import inferable
from src.i18n import t
from src.keyword_advice import keyword_advice
from src.parse.gate import checks_not_run
from src.resumes import LATEST, get_resume, resolve_cv, source_document_for_track, track_cvs
from src.tracks import get_track, list_tracks
from src.web.alerts import ceiling_remainder
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.findings import document_kind, finding_rows
from src.web.recall import query_rows
from src.web.routes.ingest import MAX_UPLOAD_BYTES
from src.web.templating import render

router = APIRouter()

# The form's own fields. `resume_id` is "latest" (resolved to the newest CV at submit,
# F11.3) or a résumé id.
EMPTY_FORM = {"jd_text": "", "company": "", "title": "", "track_id": "", "resume_id": LATEST}


def _form(
    request: Request,
    user,
    session,
    profile,
    *,
    values: dict | None = None,
    error: str | None = None,
    proposal: dict | None = None,
):
    """The form: track → CV → posting (F11.3).

    A re-rendered form (a validation error, "Proponer línea", the no-script "Ver los CV")
    keeps exactly what was submitted. With exactly one active track that track is
    preselected, since there is nothing to choose between.
    """
    tracks = list_tracks(profile.id, session, active_only=True)
    submitted = {**EMPTY_FORM, **(values or {})}
    if len(tracks) == 1 and not submitted["track_id"]:
        submitted["track_id"] = str(tracks[0].id)
    chosen = (
        get_track(profile.id, session, submitted["track_id"]) if submitted["track_id"] else None
    )
    return render(
        request,
        "analyze/form.html",
        user=user,
        profile=profile,
        values=submitted,
        active_bullets=len(list_bullets(profile.id, session, active_only=True)),
        tracks=tracks,
        cv_track=chosen,
        cvs=track_cvs(profile.id, session, chosen.id) if chosen is not None else [],
        cv_choice=submitted["resume_id"],
        proposal=proposal,
        can_analyze=model_configured(),
        error=error,
    )


def _owned_track(profile, session, track_id: str | None):
    """The track a form or URL names; another profile's is a 404, never a fallback."""
    track = get_track(profile.id, session, track_id) if track_id else None
    if track_id and track is None:
        raise HTTPException(status_code=404)
    return track


@router.get("/analyze")
def analyze_form(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    application: str | None = None,
    track_id: str | None = None,
):
    """The form, optionally pre-filled from a previous analysis (PRD §12.1 item 1).

    "Analizar con otro puesto" carries the posting, the company and the title over so
    the same JD can be scored against a different track. The id is as untrusted as any
    other: owner-scoped, and another profile's is a 404, not a redirect. `track_id`
    chooses a track (the no-script path of F11.3), with the same rule.
    """
    values: dict | None = None
    if application:
        previous = get_application(profile.id, session, application)
        if previous is None:
            return render(request, "not_found.html", user=user, status_code=404)
        values = {
            "jd_text": previous.jd_text or "",
            "company": previous.company or "",
            "title": previous.title or "",
        }
    track = _owned_track(profile, session, track_id)
    if track is not None:
        values = {**(values or {}), "track_id": str(track.id)}
    return _form(request, user, session, profile, values=values)


@router.get("/analyze/cvs")
def analyze_cvs(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    track_id: str | None = None,
):
    """The CV picker for a track (F11.3): a partial, and never a provider call."""
    track = _owned_track(profile, session, track_id)
    return render(
        request,
        "analyze/_cvs.html",
        user=user,
        cv_track=track,
        cvs=track_cvs(profile.id, session, track.id) if track is not None else [],
        cv_choice=LATEST,
    )


def _submitted(
    jd_text: str,
    company: str | None,
    title: str | None,
    track_id: str | None,
    resume_id: str | None,
) -> dict:
    return {
        "jd_text": jd_text,
        "company": company or "",
        "title": title or "",
        "track_id": track_id or "",
        "resume_id": (resume_id or "").strip() or LATEST,
    }


@router.post("/analyze/track")
def analyze_choose_track(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    jd_text: Annotated[str, Form()] = "",
    company: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    track_id: Annotated[str | None, Form()] = None,
):
    """The no-script step of F11.3: the track is submitted first and the form comes back
    with that track's CVs. Nothing is analysed and no provider is called."""
    _owned_track(profile, session, track_id)
    values = _submitted(jd_text, company, title, track_id, None)
    return _form(request, user, session, profile, values=values)


@router.post("/analyze/propose-track")
def analyze_propose_track(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    jd_text: Annotated[str, Form()] = "",
    company: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form()] = None,
    track_id: Annotated[str | None, Form()] = None,
):
    """"Proponer línea" (F11.6): a cheap ranking, not an analysis.

    The posting is extracted (one call, cached — the analysis that follows reuses it for
    free, and pressing this again costs nothing) and every active track with a CV is
    scored on that CV's Title and Keywords, deterministically. No grading call. The first
    track is preselected; the user confirms the track and the CV before analysing.
    """
    _owned_track(profile, session, track_id)
    values = _submitted(jd_text, company, title, track_id, None)
    if not jd_text.strip():
        message = t("analyze.need_text", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    try:
        prepared = prepare(
            profile.id, session, jd_text=jd_text, options=CallOptions(profile_id=profile.id)
        )
    except NoModelConfigured:
        message = t("analyze.no_model", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    except (ProviderUnavailable, StructuredOutputError):
        session.commit()
        message = t("analyze.failed", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    session.commit()
    ranked = rank_tracks(profile.id, session, prepared=prepared)
    if ranked:
        values["track_id"] = str(ranked[0].track.id)
    proposal = {
        "rows": [
            {
                "name": row.track.name,
                "title": round(row.title * 100),
                "keywords": round(row.keywords * 100),
                "cv": row.resume.filename,
            }
            for row in ranked
        ]
    }
    return _form(request, user, session, profile, values=values, proposal=proposal)


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
    resume_id: Annotated[str | None, Form()] = None,
):
    """Analyse a posting against one CV of one track (F11.3).

    An id from a form is as untrusted as one from a URL: a track or a CV that is not this
    profile's, or a CV that is not one of that track's, is a 404 — an analysis silently
    run on another file would be a wrong answer, not a degraded one. "Último CV de la
    línea" is resolved to the newest CV here, at submit.
    """
    values = _submitted(jd_text, company, title, track_id, resume_id)
    if not jd_text.strip():
        message = t("analyze.need_text", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    track = _owned_track(profile, session, track_id)
    if track is None:
        message = t("analyze.need_track", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)

    choice = values["resume_id"]
    resume = resolve_cv(profile.id, session, track.id, choice)
    if resume is None:
        if choice == LATEST and not track_cvs(profile.id, session, track.id):
            # A track with no CV cannot be analysed (F11.3): say so; the form links to
            # Importar CV with this track chosen.
            message = t("analyze.no_cv", user.ui_lang)
            return _form(request, user, session, profile, values=values, error=message)
        raise HTTPException(status_code=404)

    return _run_analysis(
        request,
        user,
        session,
        profile,
        values=values,
        track=track,
        resume=resume,
        choice=choice,
    )


def _run_analysis(request, user, session, profile, *, values, track, resume, choice):
    """Analyse `values["jd_text"]` on `resume` and store it; the page, or the form again.

    Shared by the form (F11.3) and by "Analizar con este CV" / the report's CV selector
    (`/applications/{id}/reanalyze`, F11.3, F11.7), which differ only in where the posting
    comes from. The calls that did succeed before a failure were paid for and are valid cache
    entries, so the ledger keeps them even though no application was produced.
    """
    jd_text = values["jd_text"]
    try:
        # F2.8: the ledger rows of every call this analysis makes record whose call
        # they were — attribution rides `options`.
        analysis = analyze_cv(
            profile.id,
            session,
            jd_text=jd_text,
            company=values["company"] or None,
            title=values["title"] or None,
            track=track,
            resume=resume,
            chosen="latest" if choice == LATEST else "explicit",
            options=CallOptions(profile_id=profile.id),
        )
    except NoModelConfigured:
        message = t("analyze.no_model", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    except (ProviderUnavailable, StructuredOutputError, CitationViolation):
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
        track_id=track.id,
        resume_id=resume.id,
        # The findings of the CV that capped the score, if one did (F5.1). The report
        # already carries the same JSON under `gate`; the column is what the report page
        # reads, and what N4's boolean recall will sit beside.
        scan_readability=analysis.report.get("gate"),
        # Scan B (F5.2): the queries and what they found, beside the score and never in
        # it. The report carries the same JSON for the snapshot the page renders.
        scan_boolean=analysis.report.get("recall"),
    )
    session.commit()
    return RedirectResponse(f"/applications/{application.id}", status_code=303)


@router.post("/applications/{application_id}/reanalyze")
def application_reanalyze(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    resume_id: Annotated[str | None, Form()] = None,
):
    """The same posting, on another CV of the same track: a new application (F11.3).

    JD extraction and the recruiter's queries are cached; grading costs one call unless the
    cache has it, and the gap prose usually one more ("hasta 2 llamadas"). The CV id is as
    untrusted as any other: not this profile's, or not of this application's track, is a
    404. An analysis made before F11 had no CV; the form is shown again to choose one.
    """
    previous = get_application(profile.id, session, application_id)
    if previous is None:
        return render(request, "not_found.html", user=user, status_code=404)
    choice = (resume_id or "").strip() or LATEST
    track = get_track(profile.id, session, previous.track_id) if previous.track_id else None
    values = _submitted(
        previous.jd_text or "",
        previous.company,
        previous.title,
        str(track.id) if track is not None else "",
        choice,
    )
    if track is None:
        message = t("analyze.reanalyse_no_track", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)
    resume = resolve_cv(profile.id, session, track.id, choice)
    if resume is None:
        if choice == LATEST and not track_cvs(profile.id, session, track.id):
            message = t("analyze.no_cv", user.ui_lang)
            return _form(request, user, session, profile, values=values, error=message)
        raise HTTPException(status_code=404)
    if resume.id == previous.resume_id:
        # The report already scored this CV on this posting: no duplicate, no second payment.
        return RedirectResponse(f"/applications/{previous.id}", status_code=303)
    return _run_analysis(
        request, user, session, profile, values=values, track=track, resume=resume, choice=choice
    )


@router.get("/applications/{application_id}")
def application_report(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    attempt: str | None = None,
    discarded: str | None = None,
    summary_saved: str | None = None,
):
    application = get_application(profile.id, session, application_id)
    if application is None:
        return render(request, "not_found.html", user=user, status_code=404)
    attempt_rows = list_attempt_rows(profile.id, session, application.id)
    # F10.7: a no-JS "Descartar" lands on `?discarded=<attempt_no>` and the page says so
    # without opening the modal. A number that is not one of this application's attempts
    # says nothing.
    discarded_no = (
        int(discarded)
        if discarded is not None
        and discarded.isascii()
        and discarded.isdigit()
        and any(row.attempt_no == int(discarded) for row in attempt_rows)
        else None
    )
    # F10.1/F10.7: `?attempt=<id>` reopens the modal on that attempt after a no-JS
    # action. An id that is not one of this application's attempts is ignored.
    open_attempt = attempt if any(str(row.id) == attempt for row in attempt_rows) else None
    # The readability panel names the checks the file's format could not answer, so it
    # needs the source document's kind — the résumé the track was built from.
    # On a CV analysis the document is the CV itself (F11.4); an older one is read through
    # the track's latest upload, as it always was.
    if application.resume_id:
        source = get_resume(profile.id, session, application.resume_id)
    else:
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
    ceiling, ceiling_recomputed = shown_ceiling(
        profile.id, session, report=application.report, track=track
    )
    # F11.4: an analysis of a CV is of a file, so its advice and its Keywords card are
    # worded for one ("en tu documento"), as an attempt's are.
    cv_report = bool(application.report.get("cv"))
    cv_header = application.report.get("cv") or {}
    # F11.3: the report's selector offers the track's CVs; F11.8: an analysis made before F11
    # offers them too, since re-analysing it is a new analysis on a CV.
    cv_choices = (
        track_cvs(profile.id, session, application.track_id) if application.track_id else []
    )
    # Decision 5 of STOP 0: the analysis scored the draft as it was; if the CV's draft has
    # been edited since, the page says the figures are the old ones.
    cv_edited = bool(
        source is not None
        and application.resume_id
        and cv_header.get("draft_sha")
        and source.draft
        and draft_digest(source.draft) != cv_header["draft_sha"]
    )
    keywords = keyword_advice(
        profile.id, session, report=application.report, track=track, for_file=cv_report
    )
    return render(
        request,
        "analyze/report.html",
        user=user,
        profile=profile,
        application=application,
        report=application.report,
        ceiling=ceiling,
        ceiling_recomputed=ceiling_recomputed,
        ceiling_remainder=ceiling_remainder(ceiling, user.ui_lang) if ceiling else None,
        advice_for_file=cv_report,
        cv_choices=cv_choices,
        cv_edited=cv_edited,
        # F10.1: the modal lists the attempts this analysis already has.
        attempts=application_attempts_report(attempt_rows),
        open_attempt=open_attempt,
        discarded_no=discarded_no,
        # §12.5: the summary pop-up's "Aceptar" redirects here and the page says it saved.
        summary_saved=summary_saved == "1",
        # F7.5: the Keywords card, computed now from the stored report and the user's
        # current material — deterministic, no model call, nothing written.
        keywords=keywords,
        # F7.5: the probable-keywords button, offered when keywords are left over and a model
        # is configured; otherwise the card says why not.
        infer_left=len(inferable(session, keywords)),
        infer_ready=model_configured(),
        # §12.4: the drop zone checks the size before anything is sent.
        max_upload_bytes=MAX_UPLOAD_BYTES,
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
