"""Data access for stories.

Stories are a separate store from bullets on purpose (PRD 3): compressing a story
into a one-line bullet is the main way invented metrics appear, so the two never
share a field.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.models import Bullet, Story, StoryBullet
from src.scoping import owned_row, owned_rows


def list_stories(profile_id: uuid.UUID, session: Session) -> list[Story]:
    return sorted(owned_rows(Story, session, profile_id), key=lambda story: story.title.lower())


def get_story(profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID) -> Story | None:
    return owned_row(Story, session, profile_id, story_id)


def create_story(
    profile_id: uuid.UUID,
    session: Session,
    *,
    title: str,
    body: str,
    role_id: uuid.UUID | None = None,
    tags: Iterable[str] = (),
    lang: str = "es",
) -> Story:
    story = Story(
        profile_id=profile_id,
        role_id=role_id,
        title=title.strip(),
        body=body.strip(),
        tags=[tag.strip().lower() for tag in tags if tag.strip()],
        lang=lang,
    )
    session.add(story)
    session.flush()
    return story


def update_story(
    profile_id: uuid.UUID,
    session: Session,
    story_id: str | uuid.UUID,
    *,
    title: str,
    body: str,
    role_id: uuid.UUID | None = None,
    tags: Iterable[str] = (),
    lang: str = "es",
) -> Story | None:
    story = get_story(profile_id, session, story_id)
    if story is None:
        return None
    story.title = title.strip()
    story.body = body.strip()
    story.role_id = role_id
    story.tags = [tag.strip().lower() for tag in tags if tag.strip()]
    story.lang = lang
    session.flush()
    return story


def delete_story(profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID) -> bool:
    story = get_story(profile_id, session, story_id)
    if story is None:
        return False
    session.execute(delete(StoryBullet).where(StoryBullet.story_id == story.id))
    session.delete(story)
    session.flush()
    return True


def linked_bullet_ids(
    profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID
) -> list[uuid.UUID]:
    story = get_story(profile_id, session, story_id)
    if story is None:
        return []
    return list(
        session.scalars(select(StoryBullet.bullet_id).where(StoryBullet.story_id == story.id))
    )


def linked_bullets(
    profile_id: uuid.UUID, session: Session, story_id: str | uuid.UUID
) -> list[Bullet]:
    """The story's bullets, still filtered by owner — a link never widens access."""
    ids = linked_bullet_ids(profile_id, session, story_id)
    if not ids:
        return []
    stmt = select(Bullet).where(Bullet.profile_id == profile_id, Bullet.id.in_(ids))
    return list(session.scalars(stmt))


def set_linked_bullets(
    profile_id: uuid.UUID,
    session: Session,
    story_id: str | uuid.UUID,
    bullet_ids: Sequence[str | uuid.UUID],
) -> list[Bullet]:
    """Replace the story's bullet links, ignoring ids this profile does not own."""
    story = get_story(profile_id, session, story_id)
    if story is None:
        return []
    wanted = [str(value) for value in bullet_ids if value]
    owned = (
        list(
            session.scalars(
                select(Bullet).where(
                    Bullet.profile_id == profile_id,
                    Bullet.id.in_([uuid.UUID(value) for value in wanted]),
                )
            )
        )
        if wanted
        else []
    )
    session.execute(delete(StoryBullet).where(StoryBullet.story_id == story.id))
    for bullet in owned:
        session.add(StoryBullet(story_id=story.id, bullet_id=bullet.id))
    session.flush()
    return owned
