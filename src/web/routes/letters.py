"""Letter templates: user-created reusable blocks (PRD F3)."""

from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.deletion import delete_letter_template, impact_letter_template
from src.i18n import t
from src.letters import create_letter, get_letter, list_letters, update_letter
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.templating import render

router = APIRouter()


@router.get("/letters")
def letters_list(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(
        request,
        "letters/list.html",
        user=user,
        profile=profile,
        letters=list_letters(profile.id, session),
    )


@router.get("/letters/new")
def letter_new(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return render(request, "letters/form.html", user=user, profile=profile, letter=None)


@router.post("/letters")
def letter_create(
    session: DbSession,
    profile: OwnProfile,
    name: Annotated[str, Form()],
    applies_when: Annotated[str, Form()],
    presentation: Annotated[str, Form()],
    achievements: Annotated[str, Form()],
    lang: Annotated[str | None, Form()] = None,
):
    letter = create_letter(
        profile.id,
        session,
        name=name,
        applies_when=applies_when,
        presentation=presentation,
        achievements=achievements,
        lang=(lang or "es")[:5],
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
    return render(request, "letters/form.html", user=user, profile=profile, letter=letter)


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
