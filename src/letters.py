"""Data access for letter templates.

A user may have one or twenty; the template-selection step (F6) reads
`applies_when` to choose, so there is no built-in taxonomy here.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import LetterSettings, LetterTemplate, Track
from src.scoping import owned_row, owned_rows


def list_letters(profile_id: uuid.UUID, session: Session) -> list[LetterTemplate]:
    return sorted(
        owned_rows(LetterTemplate, session, profile_id), key=lambda letter: letter.name.lower()
    )


def get_letter(
    profile_id: uuid.UUID, session: Session, letter_id: str | uuid.UUID
) -> LetterTemplate | None:
    return owned_row(LetterTemplate, session, profile_id, letter_id)


def _owned_track_id(
    profile_id: uuid.UUID, session: Session, track_id: uuid.UUID | str | None
) -> uuid.UUID | None:
    """The link only if the track is this profile's; a foreign id links nothing."""
    if track_id is None or str(track_id).strip() == "":
        return None
    track: Track | None = owned_row(Track, session, profile_id, track_id)
    return track.id if track is not None else None


def create_letter(
    profile_id: uuid.UUID,
    session: Session,
    *,
    name: str,
    applies_when: str,
    presentation: str,
    achievements: str,
    lang: str = "es",
    track_id: uuid.UUID | str | None = None,
) -> LetterTemplate:
    letter = LetterTemplate(
        profile_id=profile_id,
        name=name.strip(),
        applies_when=applies_when.strip(),
        presentation=presentation.strip(),
        achievements=achievements.strip(),
        lang=lang,
        track_id=_owned_track_id(profile_id, session, track_id),
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
    track_id: uuid.UUID | str | None = None,
) -> LetterTemplate | None:
    letter = get_letter(profile_id, session, letter_id)
    if letter is None:
        return None
    letter.name = name.strip()
    letter.applies_when = applies_when.strip()
    letter.presentation = presentation.strip()
    letter.achievements = achievements.strip()
    letter.lang = lang
    letter.track_id = _owned_track_id(profile_id, session, track_id)
    session.flush()
    return letter


def list_letter_settings(profile_id: uuid.UUID, session: Session) -> list[LetterSettings]:
    """The common blocks this profile has written, one row per language."""
    return sorted(
        owned_rows(LetterSettings, session, profile_id), key=lambda entry: entry.lang
    )


def get_letter_settings(
    profile_id: uuid.UUID, session: Session, lang: str
) -> LetterSettings | None:
    """The blocks for one language, or None — never another profile's row."""
    return session.scalar(
        select(LetterSettings).where(
            LetterSettings.profile_id == profile_id, LetterSettings.lang == (lang or "es")[:5]
        )
    )


def save_letter_settings(
    profile_id: uuid.UUID,
    session: Session,
    *,
    lang: str,
    header: str,
    greeting: str,
    closing: str,
    sign_off: str,
    voice_notes: str = "",
) -> LetterSettings:
    """Upsert the blocks for this language: one row per profile and language (F8)."""
    entry = get_letter_settings(profile_id, session, lang)
    if entry is None:
        entry = LetterSettings(profile_id=profile_id, lang=(lang or "es")[:5])
        session.add(entry)
    entry.header = header.strip()
    entry.greeting = greeting.strip()
    entry.closing = closing.strip()
    entry.sign_off = sign_off.strip()
    entry.voice_notes = voice_notes.strip()
    session.flush()
    return entry



