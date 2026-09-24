"""Tracks: list, detail, create, edit, clone, deactivate, bullet selection (PRD F4).

A track's bullet selection is posted as a set of ticks plus a number per row, so the
form needs no JavaScript and no drag-and-drop: `pick` carries the checked ids, `row`
and `rank` carry every rendered row in screen order. The number is the order the
user wants; a row left unnumbered keeps its screen position and lands after the
numbered ones.

The rest of the form is the whole CV the track presents (F4.1): a headline per
language, a summary per language picked from the pool or written new (a written one
joins the pool, so another track can reuse it), and a skill selection from the
profile's pool. Nothing here stores free text on the track — the track references
pool rows, and an id that is not this profile's is dropped by the data layer.
"""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.resumes import get_resume
from src.roles import list_roles
from src.summaries import create_summary, get_summary, list_summaries
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
from src.vocabulary import SKILL_KINDS, list_skills
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import is_checked, parse_uuid, parse_uuids
from src.web.templating import render

router = APIRouter()


def _summary_rows(session, profile) -> dict[str, list[dict]]:
    """The pool's rows per language, labelled by origin for the picker (F4.1).

    Retired rows are listed too: a track whose slot references one keeps showing
    what it shows, and the picker must never silently drop a stored choice.
    """
    rows: dict[str, list[dict]] = {"es": [], "en": []}
    for entry in list_summaries(profile.id, session, active_only=False):
        source = (
            get_resume(profile.id, session, entry.source_resume_id)
            if entry.source_resume_id
            else None
        )
        rows.setdefault(entry.lang, []).append(
            {"id": entry.id, "text": entry.text, "file": source.filename if source else None}
        )
    return rows


def _skill_groups(session, profile) -> list[tuple[str, list[str]]]:
    """The profile's skills pool grouped by `skills.kind` (F4.1).

    The pool is the ceiling: a skill no upload or manual entry ever listed is not
    in this list and cannot be added to a track here.
    """
    kinds = {skill.canonical: skill.kind for skill in list_skills(session)}
    groups: dict[str, list[str]] = {}
    for canonical in sorted(profile.skills):
        groups.setdefault(kinds.get(canonical, "technical"), []).append(canonical)
    return [(kind, groups[kind]) for kind in SKILL_KINDS if kind in groups]


def _form_context(request: Request, user, session, profile, *, track):
    return render(
        request,
        "tracks/form.html",
        user=user,
        profile=profile,
        track=track,
        summary_rows=_summary_rows(session, profile),
        skill_groups=_skill_groups(session, profile),
    )


def _slot(
    session, profile, *, picked: str | None, fresh: str | None, lang: str
) -> uuid.UUID | None:
    """One summary slot: a written-new row wins and joins the pool (F2.7)."""
    text = (fresh or "").strip()
    if text:
        return create_summary(profile.id, session, text=text, lang=lang).id
    return parse_uuid(picked)


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
def track_new(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return _form_context(request, user, session, profile, track=None)


@router.post("/tracks")
def track_create(
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    target_seniority: Annotated[str | None, Form()] = None,
    organisation_kind: Annotated[str | None, Form()] = None,
    specialisation: Annotated[str | None, Form()] = None,
    headline_es: Annotated[str | None, Form()] = None,
    headline_en: Annotated[str | None, Form()] = None,
    summary_es_id: Annotated[str | None, Form()] = None,
    summary_en_id: Annotated[str | None, Form()] = None,
    summary_es_new: Annotated[str | None, Form()] = None,
    summary_en_new: Annotated[str | None, Form()] = None,
    skill: Annotated[list[str] | None, Form()] = None,
):
    track = create_track(
        profile.id,
        session,
        name=name,
        applies_when=applies_when or "",
        lang=lang or "es",
        target_seniority=target_seniority,
        organisation_kind=organisation_kind,
        specialisation=specialisation,
        headline_es=headline_es,
        headline_en=headline_en,
        summary_es_id=_slot(
            session, profile, picked=summary_es_id, fresh=summary_es_new, lang="es"
        ),
        summary_en_id=_slot(
            session, profile, picked=summary_en_id, fresh=summary_en_new, lang="en"
        ),
        skills=skill or [],
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
        summary_es=_summary(session, profile, track.summary_es_id),
        summary_en=_summary(session, profile, track.summary_en_id),
    )


def _summary(session, profile, summary_id):
    if not summary_id:
        return None
    return get_summary(profile.id, session, summary_id)


@router.get("/tracks/{track_id}/edit")
def track_edit(
    track_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    track = get_track(profile.id, session, track_id)
    if track is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _form_context(request, user, session, profile, track=track)


@router.post("/tracks/{track_id}")
def track_save(
    track_id: str,
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    target_seniority: Annotated[str | None, Form()] = None,
    organisation_kind: Annotated[str | None, Form()] = None,
    specialisation: Annotated[str | None, Form()] = None,
    headline_es: Annotated[str | None, Form()] = None,
    headline_en: Annotated[str | None, Form()] = None,
    summary_es_id: Annotated[str | None, Form()] = None,
    summary_en_id: Annotated[str | None, Form()] = None,
    summary_es_new: Annotated[str | None, Form()] = None,
    summary_en_new: Annotated[str | None, Form()] = None,
    skill: Annotated[list[str] | None, Form()] = None,
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
        organisation_kind=organisation_kind,
        specialisation=specialisation,
        headline_es=headline_es,
        headline_en=headline_en,
        summary_es_id=_slot(
            session, profile, picked=summary_es_id, fresh=summary_es_new, lang="es"
        ),
        summary_en_id=_slot(
            session, profile, picked=summary_en_id, fresh=summary_en_new, lang="en"
        ),
        skills=skill or [],
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
