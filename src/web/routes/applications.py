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
):
    """Every analysis, newest first unless asked otherwise (F9).

    Two scores under different weights are not comparable, so the table shows the
    weights version beside each number instead of blending `w1` and `w2` rows into one
    ranking.
    """
    key = sort if sort in HISTORY_SORTS else "date"
    order = "asc" if direction == "asc" else "desc"
    return render(
        request,
        "applications/list.html",
        user=user,
        profile=profile,
        rows=list_applications(profile.id, session, sort=key, direction=order),
        outcomes=OUTCOMES,
        sort=key,
        direction=order,
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