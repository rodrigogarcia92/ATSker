"""Login and logout (PRD F1). There is no registration route, by design."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.auth.service import RateLimitedError, authenticate
from src.auth.sessions import issue
from src.i18n import t
from src.web.cookies import clear_session_cookie, set_session_cookie
from src.web.deps import CurrentUser, DbSession, session_secret
from src.web.templating import render

router = APIRouter()


@router.get("/login")
def login_form(request: Request, user: CurrentUser, lang: str | None = None):
    if user is not None:
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "login.html", lang=lang)


@router.post("/login")
def login(
    request: Request,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    session: DbSession,
    user: CurrentUser,
    lang: str | None = None,
):
    try:
        authenticated = authenticate(session, email, password)
    except RateLimitedError:
        return render(
            request,
            "login.html",
            lang=lang,
            error=t("login.rate_limited", lang),
            status_code=429,
        )

    if authenticated is None:
        return render(
            request, "login.html", lang=lang, error=t("login.invalid", lang), status_code=401
        )

    response = RedirectResponse("/dashboard", status_code=303)
    set_session_cookie(response, issue(authenticated.id, session_secret()))
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response
