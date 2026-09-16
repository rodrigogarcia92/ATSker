"""Pages behind the login."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.i18n import LANGUAGES
from src.profiles import get_own_profile, get_profile
from src.web.deps import CurrentUser, DbSession, SignedInUser
from src.web.templating import render

router = APIRouter()


@router.get("/")
def index(user: CurrentUser):
    return RedirectResponse("/dashboard" if user is not None else "/login", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, user: SignedInUser, session: DbSession):
    profile = get_own_profile(session, user)
    return render(request, "dashboard.html", user=user, profile=profile)


@router.get("/profile/{profile_id}")
def profile_page(profile_id: str, request: Request, user: SignedInUser, session: DbSession):
    profile = get_profile(profile_id, session, user)
    if profile is None:
        # An id that is not the session's own profile is indistinguishable from an
        # id that does not exist (PRD F1 isolation requirement).
        return render(request, "not_found.html", user=user, status_code=404)
    return render(request, "profile.html", user=user, profile=profile)


@router.post("/settings/lang")
def set_language(
    lang: Annotated[str, Form()],
    user: SignedInUser,
    session: DbSession,
):
    if lang in LANGUAGES:
        user.ui_lang = lang
        session.commit()
    return RedirectResponse("/dashboard", status_code=303)
