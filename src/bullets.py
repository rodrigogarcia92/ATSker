"""Data access for bullets.

Saving a bullet resolves its skill chips against the shared vocabulary and extracts
its metrics, so the import path (M2b) and manual entry produce identical rows.
Unknown chips are logged for alias promotion instead of being silently stored.
"""

import uuid
from collections.abc import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Bullet
from src.normalize.metrics import extract_metrics
from src.scoping import owned_row, owned_rows
from src.vocabulary import log_unmapped, resolve_bullet_terms, skills_in_text


def list_bullets(
    profile_id: uuid.UUID,
    session: Session,
    *,
    role_id: uuid.UUID | None = None,
    active_only: bool = True,
) -> list[Bullet]:
    bullets = [
        bullet
        for bullet in owned_rows(Bullet, session, profile_id, active_only=active_only)
        if role_id is None or bullet.role_id == role_id
    ]
    return sorted(bullets, key=lambda bullet: bullet.created_at or bullet.id.hex)


def get_bullet(
    profile_id: uuid.UUID, session: Session, bullet_id: str | uuid.UUID
) -> Bullet | None:
    return owned_row(Bullet, session, profile_id, bullet_id)


def suggest_skills(profile_id: uuid.UUID, session: Session, text: str) -> list[str]:
    """Deterministic pre-fill for the chip field; the user still confirms it."""
    return skills_in_text(session, text)


def create_bullet(
    profile_id: uuid.UUID,
    session: Session,
    *,
    role_id: uuid.UUID,
    text_en: str | None,
    text_es: str | None,
    chips: Iterable[str] = (),
) -> Bullet:
    canonical, unmatched = resolve_bullet_terms(session, chips)
    log_unmapped(session, unmatched)
    source = " ".join(part for part in (text_es, text_en) if part)
    bullet = Bullet(
        profile_id=profile_id,
        role_id=role_id,
        text_en=(text_en or "").strip() or None,
        text_es=(text_es or "").strip() or None,
        skills=canonical,
        metrics=extract_metrics(source),
    )
    session.add(bullet)
    session.flush()
    return bullet


def update_bullet(
    profile_id: uuid.UUID,
    session: Session,
    bullet_id: str | uuid.UUID,
    *,
    text_en: str | None,
    text_es: str | None,
    chips: Iterable[str] = (),
    active: bool = True,
) -> Bullet | None:
    bullet = get_bullet(profile_id, session, bullet_id)
    if bullet is None:
        return None
    canonical, unmatched = resolve_bullet_terms(session, chips)
    log_unmapped(session, unmatched)
    bullet.text_en = (text_en or "").strip() or None
    bullet.text_es = (text_es or "").strip() or None
    bullet.skills = canonical
    bullet.metrics = extract_metrics(
        " ".join(part for part in (bullet.text_es, bullet.text_en) if part)
    )
    bullet.active = active
    session.flush()
    return bullet


def set_bullet_active(
    profile_id: uuid.UUID, session: Session, bullet_id: str | uuid.UUID, *, active: bool
) -> Bullet | None:
    bullet = get_bullet(profile_id, session, bullet_id)
    if bullet is None:
        return None
    bullet.active = active
    session.flush()
    return bullet


def bullets_by_ids(
    profile_id: uuid.UUID, session: Session, bullet_ids: Sequence[str | uuid.UUID]
) -> list[Bullet]:
    """Only the selected bullets this profile owns — never another profile's."""
    wanted = [str(value) for value in bullet_ids if value]
    if not wanted:
        return []
    stmt = select(Bullet).where(Bullet.profile_id == profile_id)
    owned = [bullet for bullet in session.scalars(stmt) if str(bullet.id) in wanted]
    return sorted(owned, key=lambda bullet: wanted.index(str(bullet.id)))
