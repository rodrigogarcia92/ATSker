"""Roles: list, detail with its bullets, create, edit, deactivate."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.roles import create_role, get_role, list_roles, set_role_active, update_role
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked, parse_date
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
    title: Annotated[str, Form()],
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
):
    role = create_role(
        profile.id,
        session,
        employer=employer,
        title=title,
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
    title: Annotated[str, Form()],
    start_date: Annotated[str | None, Form()] = None,
    end_date: Annotated[str | None, Form()] = None,
    active: Annotated[str | None, Form()] = None,
):
    role = update_role(
        profile.id,
        session,
        role_id,
        employer=employer,
        title=title,
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
