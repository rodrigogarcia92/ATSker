"""Pages behind the login: dashboard, profile, education, vocabulary."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.deletion import (
    delete_everything,
    delete_skill,
    impact_everything,
    impact_skill,
)
from src.education import create_education, delete_education, list_educations, update_education
from src.i18n import LANGUAGES, t
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


@router.get("/profile/skills/delete")
def skill_delete_form(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    skill: Annotated[str, Query()],
):
    """F2.8's Skill row: the profile's pool and its tracks — never the shared
    vocabulary. The name travels outside the path because skill names contain `/`."""
    impact = impact_skill(profile.id, session, skill)
    if impact is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.skill", user.ui_lang, skill=skill, **impact),
        action="/profile/skills/delete",
        cancel="/profile",
        skill=skill,
    )


@router.post("/profile/skills/delete")
def skill_delete(session: DbSession, profile: OwnProfile, skill: Annotated[str, Form()]):
    if delete_skill(profile.id, session, skill) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/profile", status_code=303)


def _everything_screen(request, user, session, profile, *, error=None, status_code=200):
    impact = impact_everything(profile.id, session)
    unattributable = impact.pop("ledger_unattributable")
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.everything", user.ui_lang, **impact),
        unattributable_note=t("delete.unattributable", user.ui_lang, count=unattributable),
        action="/profile/delete",
        cancel="/profile",
        typed_word=True,
        error=error,
        status_code=status_code,
    )


@router.get("/profile/delete")
def profile_delete_form(
    request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    """F2.8's Everything row: Eliminar todo, behind the typed word."""
    return _everything_screen(request, user, session, profile)


@router.post("/profile/delete")
def profile_delete(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    confirm_word: Annotated[str, Form()] = "",
):
    if confirm_word.strip() != "ELIMINAR":
        return _everything_screen(
            request,
            user,
            session,
            profile,
            error=t("delete.typed_mismatch", user.ui_lang),
            status_code=422,
        )
    delete_everything(profile.id, session)
    session.commit()
    return RedirectResponse("/profile", status_code=303)
