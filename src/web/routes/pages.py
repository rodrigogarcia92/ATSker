"""Pages behind the login: dashboard, profile, education, vocabulary."""

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.education import create_education, delete_education, list_educations, update_education
from src.i18n import LANGUAGES
from src.letters import list_letters
from src.profiles import update_profile
from src.roles import list_roles
from src.stories import list_stories
from src.vocabulary import list_skills, list_unmapped
from src.web.deps import CurrentUser, DbSession, OwnProfile, SignedInUser
from src.web.forms import parse_date, parse_list, parse_text
from src.web.templating import render

router = APIRouter()


@router.get("/")
def index(user: CurrentUser):
    return RedirectResponse("/dashboard" if user is not None else "/login", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    roles = list_roles(profile.id, session)
    bullets = list_bullets(profile.id, session, active_only=True)
    stories = list_stories(profile.id, session)
    letters = list_letters(profile.id, session)
    educations = list_educations(profile.id, session)
    return render(
        request,
        "dashboard.html",
        user=user,
        profile=profile,
        counts={
            "roles": len(roles),
            "bullets": len(bullets),
            "stories": len(stories),
            "letters": len(letters),
            "educations": len(educations),
            "metrics": sum(len(bullet.metrics) for bullet in bullets),
        },
    )


@router.get("/profile")
def profile_page(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(
        request,
        "profile.html",
        user=user,
        profile=profile,
        educations=list_educations(profile.id, session),
    )


@router.post("/profile")
def save_profile(
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    display_name: Annotated[str, Form()],
    headline: Annotated[str | None, Form()] = None,
    summary: Annotated[str | None, Form()] = None,
    standing_risks: Annotated[str | None, Form()] = None,
):
    update_profile(
        profile.id,
        session,
        user,
        display_name=display_name,
        headline=headline,
        summary=summary,
        standing_risks=parse_list(standing_risks),
    )
    session.commit()
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/education")
def add_education(
    session: DbSession,
    profile: OwnProfile,
    institution: Annotated[str, Form()],
    degree: Annotated[str | None, Form()] = None,
    field: Annotated[str | None, Form()] = None,
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
):
    create_education(
        profile.id,
        session,
        institution=institution,
        degree=parse_text(degree),
        field=parse_text(field),
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
    )
    session.commit()
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/education/{education_id}")
def save_education(
    education_id: str,
    session: DbSession,
    profile: OwnProfile,
    institution: Annotated[str, Form()],
    degree: Annotated[str | None, Form()] = None,
    field: Annotated[str | None, Form()] = None,
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
):
    update_education(
        profile.id,
        session,
        education_id,
        institution=institution,
        degree=parse_text(degree),
        field=parse_text(field),
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
    )
    session.commit()
    return RedirectResponse("/profile", status_code=303)


@router.post("/profile/education/{education_id}/delete")
def remove_education(education_id: str, session: DbSession, profile: OwnProfile):
    delete_education(profile.id, session, education_id)
    session.commit()
    return RedirectResponse("/profile", status_code=303)


@router.get("/vocabulary")
def vocabulary(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(
        request,
        "vocabulary.html",
        user=user,
        profile=profile,
        skills=list_skills(session),
        unmapped=list_unmapped(session),
    )


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
