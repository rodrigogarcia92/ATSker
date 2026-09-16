"""Story tagging suggestions (PRD F3).

The model only ever chooses from identifiers and skill names already in the user's
profile; anything it returns outside those sets is dropped before the user sees it.
Suggestions are never applied silently — the caller renders them into a form the
user edits and submits.
"""

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.bullets import list_bullets
from src.config import get_settings
from src.extract import redaction
from src.extract.client import complete_json
from src.extract.prompts import STORY_SUGGESTION, summarize_rows
from src.models import Story
from src.roles import list_roles
from src.vocabulary import alias_map

PURPOSE = "story_suggest"


class StorySuggestionSchema(BaseModel):
    role_id: str | None = Field(default=None, description="id from the supplied role list, or null")
    bullet_ids: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    note: str = Field(default="")


@dataclass(frozen=True)
class StorySuggestion:
    role_id: uuid.UUID | None
    bullet_ids: list[uuid.UUID]
    skills: list[str]
    note: str


def suggest_story_links(
    profile_id: uuid.UUID, session: Session, story: Story, *, owner_name: str | None = None
) -> StorySuggestion:
    """Ask for tags, then discard anything the profile cannot already justify."""
    roles = list_roles(profile_id, session, active_only=True)
    bullets = list_bullets(profile_id, session, active_only=True)
    skills = sorted(alias_map(session).values())

    prompt = STORY_SUGGESTION.render(
        title=story.title,
        lang=story.lang,
        body=redaction.redact(story.body, known_names=[owner_name] if owner_name else None),
        roles=summarize_rows([f"{role.id}\t{role.title} @ {role.employer}" for role in roles]),
        bullets=summarize_rows(
            [f"{bullet.id}\t{bullet.text_es or bullet.text_en}" for bullet in bullets]
        ),
        skills=summarize_rows(skills),
    )

    completion = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=STORY_SUGGESTION.version,
        system=STORY_SUGGESTION.system,
        user=prompt,
        schema=StorySuggestionSchema,
    )

    allowed_roles = {str(role.id): role.id for role in roles}
    allowed_bullets = {str(bullet.id): bullet.id for bullet in bullets}
    allowed_skills = set(skills)
    # Model output is a proposal, not an authority: unknown ids and skills are dropped.
    chosen_role = allowed_roles.get(str(completion.data.get("role_id")))
    chosen_bullets = [
        allowed_bullets[value]
        for value in completion.data.get("bullet_ids", [])
        if value in allowed_bullets
    ]
    chosen_skills = [
        value for value in completion.data.get("skills", []) if value in allowed_skills
    ]

    note = str(completion.data.get("note") or "")
    if completion.cached:
        note = note or "sugerencia en caché"
    return StorySuggestion(
        role_id=chosen_role,
        bullet_ids=chosen_bullets,
        skills=chosen_skills,
        note=note,
    )


def suggestions_available() -> bool:
    """True when a model has been chosen for this environment (PRD 7)."""
    return bool((get_settings().openrouter_model or "").strip())
