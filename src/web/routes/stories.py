"""Stories: list, edit, delete, and model-assisted tagging that the user confirms."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from src.bullets import list_bullets
from src.extract.client import (
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    model_configured,
)
from src.extract.stories import suggest_story_links
from src.i18n import t
from src.roles import list_roles
from src.stories import (
    create_story,
    delete_story,
    get_story,
    linked_bullet_ids,
    list_stories,
    set_linked_bullets,
    update_story,
)
from src.web.deps import DbSession, OwnProfile, SignedInUser
from src.web.forms import parse_list, parse_uuids
from src.web.templating import render

router = APIRouter()


def _story_form(
    request: Request,
    user,
    session,
    profile,
    *,
    story=None,
    values: dict | None = None,
    suggestion=None,
    notice: str | None = None,
    error: str | None = None,
):
    story_values = values or {
        "title": story.title if story else "",
        "body": story.body if story else "",
        "role_id": str(story.role_id) if story and story.role_id else "",
        "tags": ", ".join(story.tags) if story else "",
        "lang": story.lang if story else (user.ui_lang or "es"),
        "bullet_ids": [str(value) for value in linked_bullet_ids(profile.id, session, story.id)]
        if story
        else [],
    }
    return render(
        request,
        "stories/form.html",
        user=user,
        profile=profile,
        story=story,
        values=story_values,
        roles=list_roles(profile.id, session, active_only=True),
        bullets=list_bullets(profile.id, session, active_only=True),
        suggestion=suggestion,
        notice=notice,
        error=error,
        can_suggest=model_configured(),
    )


@router.get("/stories")
def stories_list(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    stories = list_stories(profile.id, session)
    linked = {story.id: len(linked_bullet_ids(profile.id, session, story.id)) for story in stories}
    return render(
        request, "stories/list.html", user=user, profile=profile, stories=stories, linked=linked
    )


@router.get("/stories/new")
def story_new(request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile):
    return _story_form(request, user, session, profile)


@router.post("/stories")
def story_create(
    session: DbSession,
    profile: OwnProfile,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
    role_id: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    bullet_ids: Annotated[list[str] | None, Form()] = None,
):
    story = create_story(
        profile.id,
        session,
        title=title,
        body=body,
        role_id=uuid.UUID(role_id) if role_id else None,
        tags=parse_list(tags),
        lang=(lang or "es")[:5],
    )
    set_linked_bullets(profile.id, session, story.id, parse_uuids(bullet_ids))
    session.commit()
    return RedirectResponse(f"/stories/{story.id}", status_code=303)


@router.get("/stories/{story_id}")
def story_edit(
    story_id: str, request: Request, user: SignedInUser, session: DbSession, profile: OwnProfile
):
    story = get_story(profile.id, session, story_id)
    if story is None:
        return render(request, "not_found.html", user=user, status_code=404)
    return _story_form(request, user, session, profile, story=story)


@router.post("/stories/{story_id}")
def story_save(
    story_id: str,
    session: DbSession,
    profile: OwnProfile,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
    role_id: Annotated[str | None, Form()] = None,
    tags: Annotated[str | None, Form()] = None,
    lang: Annotated[str | None, Form()] = None,
    bullet_ids: Annotated[list[str] | None, Form()] = None,
):
    story = update_story(
        profile.id,
        session,
        story_id,
        title=title,
        body=body,
        role_id=uuid.UUID(role_id) if role_id else None,
        tags=parse_list(tags),
        lang=(lang or "es")[:5],
    )
    if story is None:
        raise HTTPException(status_code=404)
    set_linked_bullets(profile.id, session, story.id, parse_uuids(bullet_ids))
    session.commit()
    return RedirectResponse(f"/stories/{story.id}", status_code=303)


@router.post("/stories/{story_id}/delete")
def story_delete(story_id: str, session: DbSession, profile: OwnProfile):
    if not delete_story(profile.id, session, story_id):
        raise HTTPException(status_code=404)
    session.commit()
    return RedirectResponse("/stories", status_code=303)


@router.post("/stories/{story_id}/suggest")
def story_suggest(
    story_id: str,
    request: Request,
    user: SignedInUser,
    session: DbSession,
    profile: OwnProfile,
):
    """Ask the model for tags and show them in the form; nothing is saved here."""
    story = get_story(profile.id, session, story_id)
    if story is None:
        return render(request, "not_found.html", user=user, status_code=404)
    # The route owns its transaction: release the story read before the provider call.
    session.commit()
    try:
        suggestion = suggest_story_links(
            profile.id, session, story, owner_name=profile.display_name
        )
    except (NoModelConfigured, ProviderUnavailable, StructuredOutputError) as exc:
        session.rollback()
        message = (
            t("stories.suggest_no_model", user.ui_lang)
            if isinstance(exc, NoModelConfigured)
            else t("stories.suggest_failed", user.ui_lang)
        )
        return _story_form(request, user, session, profile, story=story, error=message)

    linked = list(linked_bullet_ids(profile.id, session, story.id))
    suggested_bullets = [str(value) for value in suggestion.bullet_ids] or [str(v) for v in linked]
    values = {
        "title": story.title,
        "body": story.body,
        "role_id": str(suggestion.role_id) if suggestion.role_id else "",
        "tags": ", ".join(dict.fromkeys([*story.tags, *suggestion.skills])),
        "lang": story.lang,
        "bullet_ids": suggested_bullets,
    }
    return _story_form(
        request,
        user,
        session,
        profile,
        story=story,
        values=values,
        suggestion=suggestion,
        notice=t("stories.suggest_applied", user.ui_lang),
        # The proposal is real; the ledger row may not be. Say so next to it.
        error=t("common.ledger_unrecorded", user.ui_lang) if suggestion.ledger_error else None,
    )
