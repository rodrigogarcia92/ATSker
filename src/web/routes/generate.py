"""Generated text over HTTP (PRD F7.3): propose, show the diff, accept or refuse.

Nothing is generated during an analysis and nothing is stored until the user
accepts. A proposal travels in the form as JSON; the accept route validates it again
against the database's own sources, because form text is user input and F7.3's
validators are the reason the number on the page can be trusted.
"""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.applications import get_application
from src.bullets import bullet_text
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.generation import generate_summary
from src.generate.proposals import (
    accept_summary,
    check_summary,
    grades_of,
    pool_skills,
    report_language,
)
from src.generate.validators import Violation
from src.i18n import t
from src.jd import StructuredJD
from src.summaries import get_summary
from src.tracks import get_track, track_bullets
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked
from src.web.templating import render

router = APIRouter()

# What the model being unreachable reads as. The same sentence the analysis form
# uses, because it is the same problem with the same fix.
_NO_MODEL = "analyze.no_model"


def _target(application_id: str, session, profile):
    """The application and the track a proposal would be written against."""
    application = get_application(profile.id, session, application_id)
    if application is None or application.track_id is None:
        return None, None
    return application, get_track(profile.id, session, application.track_id)


def _current(session, track, language: str) -> dict[str, Any]:
    """What the track holds in this language today — the other side of the diff."""
    slot = track.summary_en_id if language == "en" else track.summary_es_id
    summary = get_summary(track.profile_id, session, slot) if slot else None
    return {"summary": summary.text if summary is not None else None, "skills": list(track.skills)}


def _page(
    request,
    user,
    profile,
    application,
    track,
    session,
    *,
    proposal=None,
    violations: list[Violation] | None = None,
    error: str | None = None,
    refused: dict[str, Any] | None = None,
):
    language = report_language(application)
    return render(
        request,
        "generate/summary.html",
        user=user,
        profile=profile,
        application=application,
        track=track,
        language=language,
        proposal=proposal,
        proposal_json=(
            json.dumps(proposal.output, ensure_ascii=False) if proposal is not None else ""
        ),
        violations=violations or [],
        refused=refused,
        current=_current(session, track, language),
        error=error,
    )


@router.get("/applications/{application_id}/summary")
def propose_summary(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """One call, on demand: the Tier-1 proposal for this application (F7.3)."""
    application, track = _target(application_id, session, profile)
    if application is None or track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    if not model_configured():
        return _page(
            request, user, profile, application, track, session, error=t(_NO_MODEL, user.ui_lang)
        )

    language = report_language(application)
    # Everything the prompt needs is read first, then the reads are ended: a live
    # transaction must not be held across the provider call (the client refuses).
    try:
        jd = StructuredJD.model_validate(application.report.get("jd") or {})
        bullets = [
            (str(bullet.id), bullet_text(bullet, language))
            for bullet in track_bullets(profile.id, session, track.id)
        ]
        track_skills = list(track.skills)
        pool = list(pool_skills(profile.id, session))
        grades = grades_of(application)
        session.commit()
        proposal = generate_summary(
            session,
            jd=jd,
            bullets=bullets,
            track_skills=track_skills,
            pool=pool,
            grades=grades,
            language=language,
            options=CallOptions(profile_id=profile.id),
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError):
        # A paid call that failed is still paid; keep the ledger and report plainly.
        session.commit()
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            error=t("generate.failed", user.ui_lang),
        )

    session.commit()
    violations = check_summary(profile.id, session, application, track, proposal.output)
    return _page(
        request,
        user,
        profile,
        application,
        track,
        session,
        proposal=proposal,
        violations=violations,
    )


@router.post("/applications/{application_id}/summary/accept")
def accept_summary_proposal(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    payload: Annotated[str, Form()],
    use_in_track: Annotated[str | None, Form()] = None,
):
    """Accept a proposal: re-validate against the database, then write it (F7.3)."""
    application, track = _target(application_id, session, profile)
    if application is None or track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed proposal") from exc

    _, violations = accept_summary(
        profile.id,
        session,
        application,
        track,
        text=str((data.get("summary") or {}).get("text") or ""),
        cites=list((data.get("summary") or {}).get("cites") or []),
        skills=list(data.get("skills") or []),
        use_in_track=is_checked(use_in_track),
    )
    if violations:
        # Refused: shown with the rule that failed, and nothing was written.
        return _page(
            request,
            user,
            profile,
            application,
            track,
            session,
            violations=violations,
            refused=data,
            error=t("generate.refused", user.ui_lang),
        )

    session.commit()
    return RedirectResponse(f"/tracks/{track.id}", status_code=303)
