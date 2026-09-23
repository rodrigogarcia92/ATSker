"""The summary pool's edit screen (PRD F2.7, F4.1).

A track references pool rows, never owns them: editing a summary here changes the text
in every track whose slot uses it, and deactivating is the delete — a stored report that
cited the row keeps rendering it. The pool is reached from the track form's picker;
this is the screen behind each of its rows.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.summaries import get_summary, set_summary_active, update_summary
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked
from src.web.templating import render

router = APIRouter()


def _form_context(request: Request, user, profile, *, summary):
    return render(
        request,
        "summaries/form.html",
        user=user,
        profile=profile,
        summary=summary,
    )


@router.get("/summaries/{summary_id}")
def summary_edit(
    summary_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    summary = get_summary(profile.id, session, summary_id)
    if summary is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _form_context(request, user, profile, summary=summary)


@router.post("/summaries/{summary_id}")
def summary_save(
    summary_id: str,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    text: Annotated[str, Form()],
    lang: Annotated[str | None, Form()] = None,
):
    summary = get_summary(profile.id, session, summary_id)
    if summary is None:
        raise HTTPException(status_code=404)
    if not text.strip():
        raise HTTPException(status_code=422, detail="a summary needs text")
    update_summary(profile.id, session, summary_id, text=text, lang=(lang or summary.lang)[:5])
    session.commit()
    return RedirectResponse(f"/summaries/{summary_id}", status_code=303)


@router.post("/summaries/{summary_id}/active")
def summary_toggle(
    summary_id: str,
    session: DbSession,
    profile: OwnProfile,
    active: Annotated[str | None, Form()] = None,
):
    if set_summary_active(profile.id, session, summary_id, active=is_checked(active)) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse(f"/summaries/{summary_id}", status_code=303)
