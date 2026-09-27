"""Roles: list, detail with its bullets, create, edit, deactivate."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.deletion import delete_role, impact_role
from src.i18n import t
from src.roles import create_role, get_role, list_roles, set_role_active, update_role
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked, parse_date, parse_text
from src.web.templating import render

router = APIRouter()


@router.get("/roles")
def roles_list(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    roles = list_roles(profile.id, session)
    bullets = list_bullets(profile.id, session, active_only=False)
    counts = {role.id: len([b for b in bullets if b.role_id == role.id]) for role in roles}
    return render(
        request, "roles/list.html", user=user, profile=profile, roles=roles, counts=counts
    )


@router.get("/roles/new")
def role_new(request: Request, user: SignedInUser, profile: OwnProfile):
    return render(request, "roles/form.html", user=user, profile=profile, role=None)


@router.post("/roles")
def role_create(
    session: DbSession,
    profile: OwnProfile,
    employer: Annotated[str, Form()],
    title_es: Annotated[str | None, Form()] = None,
    title_en: Annotated[str | None, Form()] = None,
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
):
    # F4.2: one title per language, and one of the two has to be there — a role with
    # no title is a date range, and every screen names it.
    if not (parse_text(title_es) or parse_text(title_en)):
        raise HTTPException(status_code=422, detail="a role needs a title in one language")
    role = create_role(
        profile.id,
        session,
        employer=employer,
        title_es=parse_text(title_es),
        title_en=parse_text(title_en),
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
    )
    session.commit()
    return RedirectResponse(f"/roles/{role.id}", status_code=303)


@router.get("/roles/{role_id}")
def role_detail(
    role_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    role = get_role(profile.id, session, role_id)
    if role is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "roles/detail.html",
        user=user,
        profile=profile,
        role=role,
        bullets=list_bullets(profile.id, session, role_id=role.id, active_only=False),
    )


@router.get("/roles/{role_id}/edit")
def role_edit(
    role_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    role = get_role(profile.id, session, role_id)
    if role is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(request, "roles/form.html", user=user, profile=profile, role=role)


@router.post("/roles/{role_id}")
def role_save(
    role_id: str,
    session: DbSession,
    profile: OwnProfile,
    employer: Annotated[str, Form()],
    title_es: Annotated[str | None, Form()] = None,
    title_en: Annotated[str | None, Form()] = None,
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
    active: Annotated[str | None, Form()] = None,
):
    if not (parse_text(title_es) or parse_text(title_en)):
        raise HTTPException(status_code=422, detail="a role needs a title in one language")
    role = update_role(
        profile.id,
        session,
        role_id,
        employer=employer,
        title_es=parse_text(title_es),
        title_en=parse_text(title_en),
        start_date=parse_date(start_date),
        end_date=parse_date(end_date),
        active=is_checked(active),
    )
    if role is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse(f"/roles/{role.id}", status_code=303)


@router.post("/roles/{role_id}/active")
def role_toggle(
    role_id: str,
    session: DbSession,
    profile: OwnProfile,
    active: Annotated[str | None, Form()] = None,
):
    role = set_role_active(profile.id, session, role_id, active=is_checked(active))
    if role is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/roles", status_code=303)


@router.get("/roles/{role_id}/delete")
def role_delete_form(
    role_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    """F2.8: the confirmation screen states the consequences in numbers first."""
    impact = impact_role(profile.id, session, role_id)
    if impact is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.role", user.ui_lang, **impact),
        action=f"/roles/{role_id}/delete",
        cancel="/roles",
    )


@router.post("/roles/{role_id}/delete")
def role_delete(role_id: str, session: DbSession, profile: OwnProfile):
    if delete_role(profile.id, session, role_id) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/roles", status_code=303)
