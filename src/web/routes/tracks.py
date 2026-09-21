"""Tracks: list, detail, create, edit, clone, deactivate, bullet selection (PRD F4).

A track's selection is posted as a set of ticks plus a number per row, so the form
needs no JavaScript and no drag-and-drop: `pick` carries the checked ids, `row` and
`rank` carry every rendered row in screen order. The number is the order the user
wants; a row left unnumbered keeps its screen position and lands after the numbered
ones.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.roles import list_roles
from src.tracks import (
    clone_track,
    create_track,
    get_track,
    list_tracks,
    selection_sizes,
    set_track_active,
    set_track_bullets,
    track_bullets,
    update_track,
)
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked, parse_uuid, parse_uuids
from src.web.templating import render

router = APIRouter()


@router.get("/tracks")
def tracks_list(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    tracks = list_tracks(profile.id, session, active_only=False)
    return render(
        request,
        "tracks/list.html",
        user=user,
        profile=profile,
        tracks=tracks,
        sizes=selection_sizes(profile.id, session),
    )


@router.get("/tracks/new")
def track_new(request: Request, user: SignedInUser, profile: OwnProfile):
    return render(request, "tracks/form.html", user=user, profile=profile, track=None)


@router.post("/tracks")
def track_create(
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    target_seniority: Annotated[str | None, Form()] = None,
    headline: Annotated[str | None, Form()] = None,
    summary: Annotated[str | None, Form()] = None,
):
    track = create_track(
        profile.id,
        session,
        name=name,
        applies_when=applies_when or "",
        lang=lang or "es",
        target_seniority=target_seniority,
        headline=headline,
        summary=summary,
    )
    session.commit()
    return RedirectResponse(f"/tracks/{track.id}", status_code=303)


@router.get("/tracks/{track_id}")
def track_detail(
    track_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    track = get_track(profile.id, session, track_id)
    if track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "tracks/detail.html",
        user=user,
        profile=profile,
        track=track,
        bullets=track_bullets(profile.id, session, track.id),
    )


@router.get("/tracks/{track_id}/edit")
def track_edit(
    track_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    track = get_track(profile.id, session, track_id)
    if track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(request, "tracks/form.html", user=user, profile=profile, track=track)


@router.post("/tracks/{track_id}")
def track_save(
    track_id: str,
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    target_seniority: Annotated[str | None, Form()] = None,
    headline: Annotated[str | None, Form()] = None,
    summary: Annotated[str | None, Form()] = None,
    active: Annotated[str | None, Form()] = None,
):
    track = update_track(
        profile.id,
        session,
        track_id,
        name=name,
        applies_when=applies_when or "",
        lang=lang or "es",
        target_seniority=target_seniority,
        headline=headline,
        summary=summary,
        active=is_checked(active),
    )
    if track is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse(f"/tracks/{track.id}", status_code=303)


@router.post("/tracks/{track_id}/clone")
def track_clone(
    track_id: str, session: DbSession, profile: OwnProfile, name: Annotated[str, Form()]
):
    source = get_track(profile.id, session, track_id)
    if source is None:
        raise HTTPException(status_code=404)
    clone = clone_track(profile.id, session, track_id, name=name.strip() or source.name)
    session.commit()
    return RedirectResponse(f"/tracks/{clone.id}", status_code=303)


@router.post("/tracks/{track_id}/active")
def track_toggle(
    track_id: str,
    session: DbSession,
    profile: OwnProfile,
    active: Annotated[str | None, Form()] = None,
):
    track = set_track_active(profile.id, session, track_id, active=is_checked(active))
    if track is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse(f"/tracks/{track.id}", status_code=303)


@router.get("/tracks/{track_id}/bullets")
def track_bullet_picker(
    track_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    track = get_track(profile.id, session, track_id)
    if track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    selected = track_bullets(profile.id, session, track.id)
    by_role: dict[uuid.UUID, list] = {}
    for bullet in list_bullets(profile.id, session, active_only=True):
        by_role.setdefault(bullet.role_id, []).append(bullet)
    groups = [
        (role, by_role[role.id])
        for role in list_roles(profile.id, session, active_only=False)
        if role.id in by_role
    ]
    return render(
        request,
        "tracks/bullets.html",
        user=user,
        profile=profile,
        track=track,
        groups=groups,
        positions={bullet.id: index + 1 for index, bullet in enumerate(selected)},
    )


@router.post("/tracks/{track_id}/bullets")
def track_bullets_save(
    track_id: str,
    session: DbSession,
    profile: OwnProfile,
    pick: Annotated[list[str] | None, Form()] = None,
    row: Annotated[list[str] | None, Form()] = None,
    rank: Annotated[list[str] | None, Form()] = None,
):
    if get_track(profile.id, session, track_id) is None:
        raise HTTPException(status_code=404)
    chosen = ordered_selection(rows=row or [], ranks=rank or [], picked=pick or [])
    set_track_bullets(profile.id, session, track_id, chosen)
    session.commit()
    return RedirectResponse(f"/tracks/{track_id}", status_code=303)


def ordered_selection(
    *, rows: Sequence[str], ranks: Sequence[str], picked: Sequence[str]
) -> list[uuid.UUID]:
    """The checked rows, ordered by their number, tie-broken by screen order.

    Only ids the form actually rendered can enter the selection, so a hand-made post
    cannot add anything — and `set_track_bullets` still drops another profile's rows.
    """
    checked = set(parse_uuids(picked))
    unnumbered = len(rows) + 1
    chosen: list[tuple[int, int, uuid.UUID]] = []
    for index, raw in enumerate(rows):
        bullet_id = parse_uuid(raw)
        if bullet_id is None or bullet_id not in checked:
            continue
        value = (ranks[index] if index < len(ranks) else "").strip()
        number = int(value) if value.isdigit() and int(value) > 0 else unnumbered
        chosen.append((number, index, bullet_id))
    chosen.sort(key=lambda entry: (entry[0], entry[1]))
    return [bullet_id for _, _, bullet_id in chosen]
