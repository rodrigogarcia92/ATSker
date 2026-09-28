"""Application history (PRD F9): the leaderboard view and its editable outcome.

The table is the dataset: every analysis is already persisted with its score, its
track and its cost, and after enough applications it is what answers whether the
sub-scores predict callbacks. Sorting is server-side — a column is a URL, not a
script — and an unknown column falls back to the default view rather than raising.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from src.applications import HISTORY_SORTS, OUTCOMES, list_applications, set_application_outcome
from src.deletion import delete_application, impact_application
from src.i18n import t
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()


@router.get("/applications")
def applications_list(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    sort: str = "date",
    direction: Annotated[str, Query(alias="dir")] = "desc",
    outcome: str | None = None,
):
    """Every analysis, newest first unless asked otherwise (F9).

    Two scores under different weights are not comparable, so the table shows the
    weights version beside each number instead of blending `w1` and `w2` rows into one
    ranking. `?outcome=none` narrows it to the analyses still waiting on a result
    (F.1); any other value outside F9's five is ignored rather than refused.
    """
    key = sort if sort in HISTORY_SORTS else "date"
    order = "asc" if direction == "asc" else "desc"
    selected = outcome if outcome in (*OUTCOMES, "none") else None
    return render(
        request,
        "applications/list.html",
        user=user,
        profile=profile,
        rows=list_applications(profile.id, session, sort=key, direction=order, outcome=selected),
        outcomes=OUTCOMES,
        sort=key,
        direction=order,
        outcome=selected,
    )


@router.post("/applications/{application_id}/outcome")
def application_outcome(
    application_id: str,
    session: DbSession,
    profile: OwnProfile,
    outcome: Annotated[str, Form()],
):
    """Record what happened. Only F9's five values are outcomes; anything else is a 400."""
    if outcome not in OUTCOMES:
        raise HTTPException(status_code=400, detail="unknown outcome")
    if set_application_outcome(profile.id, session, application_id, outcome=outcome) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/applications", status_code=303)


@router.get("/applications/{application_id}/delete")
def application_delete_form(
    application_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    impact = impact_application(profile.id, session, application_id)
    if impact is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.application", user.ui_lang, **impact),
        action=f"/applications/{application_id}/delete",
        cancel="/applications",
    )


@router.post("/applications/{application_id}/delete")
def application_delete(application_id: str, session: DbSession, profile: OwnProfile):
    if delete_application(profile.id, session, application_id) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/applications", status_code=303)