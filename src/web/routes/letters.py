"""Letter templates and their blocks (PRD F3, F8)."""

import json
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.deletion import delete_letter_template, impact_letter_template
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.generation import generate_letter_blocks
from src.generate.letters import accept_blocks, block_material, check_blocks
from src.generate.validators import Violation
from src.i18n import t
from src.letters import (
    create_letter,
    get_letter,
    get_letter_settings,
    list_letters,
    save_letter_settings,
    update_letter,
)
from src.tracks import get_track, list_tracks
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


# --- N8.3: propose a template's presentation and achievements ----------------------


def voice_notes_for(profile_id, session, lang: str) -> str:
    """The register the profile asked for, in this language (F8's voice notes)."""
    entry = get_letter_settings(profile_id, session, lang)
    return entry.voice_notes if entry is not None else ""


def _propose_page(
    request,
    user,
    profile,
    letter,
    session,
    *,
    proposal=None,
    violations: list[Violation] | None = None,
    refused: dict | None = None,
    error: str | None = None,
):
    track = get_track(profile.id, session, letter.track_id) if letter.track_id else None
    return render(
        request,
        "letters/propose.html",
        user=user,
        profile=profile,
        letter=letter,
        track=track,
        can_propose=track is not None,
        proposal=proposal,
        refused=refused,
        proposal_json=(
            json.dumps(proposal.output, ensure_ascii=False) if proposal is not None else ""
        ),
        violations=violations or [],
        run_url=(
            f"/letters/{letter.id}/propose"
            if proposal is None and refused is None and error is None and track is not None
            else None
        ),
        error=error,
    )


@router.get("/letters/{letter_id}/propose")
def letter_propose(
    letter_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """The blocks page. A GET renders the button; the provider call is the POST (F8)."""
    letter = get_letter(profile.id, session, letter_id)
    if letter is None:
        return render(request, "not_found.html", user=user, status_code=404)
    if not model_configured():
        return _propose_page(
            request, user, profile, letter, session, error=t("analyze.no_model", user.ui_lang)
        )
    return _propose_page(request, user, profile, letter, session)


@router.post("/letters/{letter_id}/propose")
def letter_propose_generate(
    letter_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """One paid call, on demand: the template's presentation and achievements (N8.3)."""
    letter = get_letter(profile.id, session, letter_id)
    if letter is None:
        return render(request, "not_found.html", user=user, status_code=404)
    track = get_track(profile.id, session, letter.track_id) if letter.track_id else None
    if track is None:
        return _propose_page(
            request,
            user,
            profile,
            letter,
            session,
            error=t("letters.propose_no_track", user.ui_lang),
        )
    if not model_configured():
        return _propose_page(
            request, user, profile, letter, session, error=t("analyze.no_model", user.ui_lang)
        )

    # Everything the prompt reads is computed first; the reads end before the call.
    material, sources = block_material(profile.id, session, track, letter.lang)
    voice_notes = voice_notes_for(profile.id, session, letter.lang)
    session.commit()
    try:
        proposal = generate_letter_blocks(
            session,
            bullets=material["bullets"],
            roles=material["roles"],
            summary=material["summary"],
            stories=material["stories"],
            voice_notes=voice_notes,
            language=letter.lang,
            options=CallOptions(profile_id=profile.id),
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError):
        session.commit()
        return _propose_page(
            request, user, profile, letter, session, error=t("generate.failed", user.ui_lang)
        )

    session.commit()
    violations = check_blocks(proposal.output, sources)
    return _propose_page(
        request, user, profile, letter, session, proposal=proposal, violations=violations
    )


@router.post("/letters/{letter_id}/propose/accept")
def letter_propose_accept(
    letter_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
    payload: Annotated[str, Form()],
):
    """Accept the blocks: re-validate against the database, then write them (N8.3)."""
    letter = get_letter(profile.id, session, letter_id)
    if letter is None:
        return render(request, "not_found.html", user=user, status_code=404)
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="malformed proposal") from exc

    _, violations = accept_blocks(profile.id, session, letter.id, data)
    if violations:
        return _propose_page(
            request,
            user,
            profile,
            letter,
            session,
            violations=violations,
            refused=data,
            error=t("generate.refused", user.ui_lang),
        )
    session.commit()
    return RedirectResponse(f"/letters/{letter.id}/edit", status_code=303)
