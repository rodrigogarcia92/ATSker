"""Data access for letter templates.

A user may have one or twenty; the template-selection step (F6) reads
`applies_when` to choose, so there is no built-in taxonomy here.
"""

import uuid

from sqlalchemy.orm import Session

from src.models import LetterTemplate
from src.scoping import owned_row, owned_rows


def list_letters(profile_id: uuid.UUID, session: Session) -> list[LetterTemplate]:
    return sorted(
        owned_rows(LetterTemplate, session, profile_id), key=lambda letter: letter.name.lower()
    )


def get_letter(
    profile_id: uuid.UUID, session: Session, letter_id: str | uuid.UUID
) -> LetterTemplate | None:
    return owned_row(LetterTemplate, session, profile_id, letter_id)


def create_letter(
    profile_id: uuid.UUID,
    session: Session,
    *,
    name: str,
    applies_when: str,
    presentation: str,
    achievements: str,
    lang: str = "es",
) -> LetterTemplate:
    letter = LetterTemplate(
        profile_id=profile_id,
        name=name.strip(),
        applies_when=applies_when.strip(),
        presentation=presentation.strip(),
        achievements=achievements.strip(),
        lang=lang,
    )
    session.add(letter)
    session.flush()
    return letter


def update_letter(
    profile_id: uuid.UUID,
    session: Session,
    letter_id: str | uuid.UUID,
    *,
    name: str,
    applies_when: str,
    presentation: str,
    achievements: str,
    lang: str = "es",
) -> LetterTemplate | None:
    letter = get_letter(profile_id, session, letter_id)
    if letter is None:
        return None
    letter.name = name.strip()
    letter.applies_when = applies_when.strip()
    letter.presentation = presentation.strip()
    letter.achievements = achievements.strip()
    letter.lang = lang
    session.flush()
    return letter


def delete_letter(profile_id: uuid.UUID, session: Session, letter_id: str | uuid.UUID) -> bool:
    letter = get_letter(profile_id, session, letter_id)
    if letter is None:
        return False
    session.delete(letter)
    session.flush()
    return True
