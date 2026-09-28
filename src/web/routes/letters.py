"""Letter templates: user-created reusable blocks (PRD F3)."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.deletion import delete_letter_template, impact_letter_template
from src.i18n import t
from src.letters import (
    create_letter,
    get_letter,
    get_letter_settings,
    list_letters,
    save_letter_settings,
    update_letter,
)
from src.tracks import list_tracks
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()


# The languages a letter may be written in: the profile's blocks are per language (F8).
LETTER_LANGS = ("es", "en")


def _groups(letters, tracks) -> list[dict]:
    """Templates grouped by the track they are linked to, unlinked last (F8, N8.2)."""
    groups: list[dict] = []
    for track in tracks:
        linked = [letter for letter in letters if letter.track_id == track.id]
        if linked:
            groups.append({"name": track.name, "track_id": track.id, "letters": linked})
    unlinked = [letter for letter in letters if letter.track_id is None]
    if unlinked:
        groups.append({"name": None, "track_id": None, "letters": unlinked})
    return groups


def _list_context(session, profile) -> dict:
    letters = list_letters(profile.id, session)
    tracks = list_tracks(profile.id, session, active_only=False)
    return {
        "letters": letters,
        "tracks": tracks,
        "groups": _groups(letters, tracks),
        "settings": [
            {"lang": lang, "entry": get_letter_settings(profile.id, session, lang)}
            for lang in LETTER_LANGS
        ],
    }


@router.get("/letters")
def letters_list(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(
        request, "letters/list.html", user=user, profile=profile, **_list_context(session, profile)
    )


@router.post("/letters/settings")
def letter_settings_save(
    session: DbSession,
    profile: OwnProfile,
    lang: Annotated[str, Form()],
    header: Annotated[str, Form()] = "",
    greeting: Annotated[str, Form()] = "",
    closing: Annotated[str, Form()] = "",
    sign_off: Annotated[str, Form()] = "",
    voice_notes: Annotated[str, Form()] = "",
):
    """The blocks every letter shares, per language (F8)."""
    save_letter_settings(
        profile.id,
        session,
        lang=(lang or "es")[:5],
        header=header,
        greeting=greeting,
        closing=closing,
        sign_off=sign_off,
        voice_notes=voice_notes,
    )
    session.commit()
    return RedirectResponse("/letters", status_code=303)


@router.get("/letters/new")
def letter_new(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(
        request,
        "letters/form.html",
        user=user,
        profile=profile,
        letter=None,
        tracks=list_tracks(profile.id, session, active_only=False),
    )


@router.post("/letters")
def letter_create(
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str, Form()],
    presentation: Annotated[str, Form()],
    achievements: Annotated[str, Form()],
    lang: Annotated[str | None, Form()] = None,
    track_id: Annotated[str | None, Form()] = None,
):
    letter = create_letter(
        profile.id,
        session,
        name=name,
        applies_when=applies_when,
        presentation=presentation,
        achievements=achievements,
        lang=(lang or "es")[:5],
        track_id=track_id,
    )
    session.commit()
    return RedirectResponse(f"/letters/{letter.id}/edit", status_code=303)


@router.get("/letters/{letter_id}/edit")
def letter_edit(
    letter_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    letter = get_letter(profile.id, session, letter_id)
    if letter is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "letters/form.html",
        user=user,
        profile=profile,
        letter=letter,
        tracks=list_tracks(profile.id, session, active_only=False),
    )


@router.post("/letters/{letter_id}")
def letter_save(
    letter_id: str,
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str, Form()],
    presentation: Annotated[str, Form()],
    achievements: Annotated[str, Form()],
    lang: Annotated[str | None, Form()] = None,
    track_id: Annotated[str | None, Form()] = None,
):
    letter = update_letter(
        profile.id,
        session,
        letter_id,
        name=name,
        applies_when=applies_when,
        presentation=presentation,
        achievements=achievements,
        lang=(lang or "es")[:5],
        track_id=track_id,
    )
    if letter is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/letters", status_code=303)


@router.get("/letters/{letter_id}/delete")
def letter_delete_form(
    letter_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    impact = impact_letter_template(profile.id, session, letter_id)
    if impact is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return render(
        request,
        "delete/confirm.html",
        user=user,
        impact_text=t("delete.impact.letter", user.ui_lang, **impact),
        action=f"/letters/{letter_id}/delete",
        cancel="/letters",
    )


@router.post("/letters/{letter_id}/delete")
def letter_delete(letter_id: str, session: DbSession, profile: OwnProfile):
    if delete_letter_template(profile.id, session, letter_id) is None:
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/letters", status_code=303)
