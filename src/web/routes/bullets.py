"""Bullets: create under a role, edit, deactivate, and skill detection.

Deactivation is the delete (PRD F2 soft delete); the row stays so historical
reports keep rendering.
"""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import (
    create_bullet,
    get_bullet,
    set_bullet_active,
    suggest_skills,
    update_bullet,
)
from src.deletion import delete_bullet, impact_bullet
from src.i18n import t
from src.roles import get_role
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked, parse_text
from src.web.templating import render

router = APIRouter()


def _form_context(
    request: Request,
    user,
    profile,
    role,
    *,
    bullet=None,
    chips: str = "",
    detected: list[str] | None = None,
    error: str | None = None,
):
    return render(
        request,
        "bullets/form.html",
        user=user,
        profile=profile,
        role=role,
        bullet=bullet,
        chips=chips,
        detected=detected or [],
        error=error,
    )


@router.get("/roles/{role_id}/bullets/new")
def bullet_new(
    role_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    role = get_role(profile.id, session, role_id)
    if role is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _form_context(request, user, profile, role)


@router.post("/roles/{role_id}/bullets")
def bullet_create(
    role_id: str,
    session: DbSession,
    profile: OwnProfile,
    text_es: Annotated[str | None, Form()] = None,
    text_en: Annotated[str | None, Form()] = None,
    chips: Annotated[str | None, Form()] = None,
):
    role = get_role(profile.id, session, role_id)
    if role is None:
        raise HTTPException(status_code=404)
    if not (parse_text(text_es) or parse_text(text_en)):
        raise HTTPException(status_code=422, detail="a bullet needs text in at least one language")
    create_bullet(
        profile.id,
        session,
        role_id=role.id,
        text_en=parse_text(text_en),
        text_es=parse_text(text_es),
        chips=[part for part in (chips or "").split(",")],
    )
    session.commit()
    return RedirectResponse(f"/roles/{role.id}", status_code=303)


@router.get("/bullets/{bullet_id}/edit")
def bullet_edit(
    bullet_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    bullet = get_bullet(profile.id, session, bullet_id)
    if bullet is None:
        return render(request, "not_found.html", user=user, status_code=404)
    role = get_role(profile.id, session, bullet.role_id)
    return _form_context(
        request, user, profile, role, bullet=bullet, chips=", ".join(bullet.skills)
    )


@router.post("/bullets/detect")
def bullet_detect(
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    role_id: Annotated[str | None, Form()] = None,
    bullet_id: Annotated[str | None, Form()] = None,
    text_es: Annotated[str | None, Form()] = None,
    text_en: Annotated[str | None, Form()] = None,
    chips: Annotated[str | None, Form()] = None,
):
    """Deterministic vocabulary lookup over the typed text; the user still submits."""
    bullet = get_bullet(profile.id, session, bullet_id) if bullet_id else None
    role = (
        get_role(profile.id, session, bullet.role_id)
        if bullet
        else get_role(profile.id, session, role_id)
    )
    if role is None:
        return render(request, "not_found.html", user=user, status_code=404)

    detected = suggest_skills(profile.id, session, f"{text_es or ''} {text_en or ''}")
    existing = [part.strip() for part in (chips or "").split(",") if part.strip()]
    combined = existing + [skill for skill in detected if skill not in existing]
    return _form_context(
        request,
        user,
        profile,
        role,
        bullet=bullet,
        chips=", ".join(combined),
        detected=detected,
    )


@router.post("/bullets/{bullet_id}")
def bullet_save(
    bullet_id: str,
    session: DbSession,
    profile: OwnProfile,
    text_es: Annotated[str | None, Form()] = None,
    text_en: Annotated[str | None, Form()] = None,
    chips: Annotated[str | None, Form()] = None,
    active: Annotated[str | None, Form()] = None,
):
    bullet = get_bullet(profile.id, session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404)
    update_bullet(
        profile.id,
        session,
        bullet_id,
        text_en=parse_text(text_en),
        text_es=parse_text(text_es),
        chips=[part for part in (chips or "").split(",")],
        active=is_checked(active),
    )
    session.commit()
    return RedirectResponse(f"/roles/{bullet.role_id}", status_code=303)


@router.post("/bullets/{bullet_id}/active")
def bullet_toggle(
    bullet_id: str,
    session: DbSession,
    profile: OwnProfile,
    active: Annotated[str | None, Form()] = None,
):
    bullet = get_bullet(profile.id, session, bullet_id)
    if bullet is None:
        raise HTTPException(status_code=404)
    set_bullet_active(profile.id, session, bullet_id, active=is_checked(active))
    session.commit()
    return RedirectResponse(f"/roles/{bullet.role_id}", status_code=303)


@router.get("/bullets/{bullet_id}/delete")
def bullet_delete_form(
    bullet_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    bullet = get_bullet(profile.id, session, bullet_id)
    if bullet is None:
        return render(request, "not_found.html", user=user, status_code=404)
    impact = impact_bullet(profile.id, session, bullet_id)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.bullet", user.ui_lang, **impact),
        action=f"/bullets/{bullet_id}/delete",
        cancel=f"/roles/{bullet.role_id}",
    )


@router.post("/bullets/{bullet_id}/delete")
def bullet_delete(bullet_id: str, session: DbSession, profile: OwnProfile):
    bullet = get_bullet(profile.id, session, bullet_id)
    if bullet is None or delete_bullet(profile.id, session, bullet_id) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse(f"/roles/{bullet.role_id}", status_code=303)
