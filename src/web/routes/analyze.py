"""The analysis page: paste a posting, get the report it produces (PRD F4/F8).

One route runs the pipeline and one renders what was stored, so the report the
user reads is the row the dataset keeps — not a re-render of live data that could
drift from it.
"""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.analysis import analyze
from src.applications import create_application, get_application
from src.bullets import list_bullets
from src.extract.client import (
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.grading import CitationViolation
from src.i18n import t
from src.score.aggregate import SUB_SCORES
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()

EMPTY_FORM = {"jd_text": "", "company": "", "title": ""}


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
):
    values = {"jd_text": jd_text, "company": company or "", "title": title or ""}
    if not jd_text.strip():
        message = t("analyze.need_text", user.ui_lang)
        return _form(request, user, session, profile, values=values, error=message)

    try:
        analysis = analyze(profile.id, session, jd_text=jd_text, company=company, title=title)
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
    return render(
        request,
        "analyze/report.html",
        user=user,
        profile=profile,
        application=application,
        report=application.report,
        sub_order=SUB_SCORES,
        component_count=len(SUB_SCORES),
    )
