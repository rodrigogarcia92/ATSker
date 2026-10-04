"""Data access for letter templates (PRD F3, F8).

A track has one template, kept in code rather than in the schema (see the F8 section
below). Templates linked to no track are old ones, kept and never used by a letter.
"""

import uuid
from collections.abc import Mapping
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.i18n import t
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


# --- F8: one template per track ------------------------------------------------------
#
# "One per track" is enforced here, not by the schema (no migration): a track's template
# is the one linked row, and the functions below never create a second one. Rows that
# already are duplicates are kept and listed; `use_template_for_track` is how the user
# picks one, and nothing is ever deleted by it.


def track_templates(
    profile_id: uuid.UUID, session: Session, track: Track
) -> list[LetterTemplate]:
    """Every template linked to this track, in the order `track_template` picks from.

    `letter_templates` has no timestamp (and a column would be a migration), so the
    order is the one the Cartas page lists them in: by name, then id. It is stable, and
    it is what "the first one" means until the user chooses.
    """
    if track.profile_id != profile_id:
        return []
    linked = [
        letter
        for letter in owned_rows(LetterTemplate, session, profile_id)
        if letter.track_id == track.id
    ]
    return sorted(linked, key=lambda letter: (letter.name.lower(), str(letter.id)))


def track_template(
    profile_id: uuid.UUID, session: Session, track: Track
) -> LetterTemplate | None:
    """The track's template: the one linked row, or the first when several are linked."""
    linked = track_templates(profile_id, session, track)
    return linked[0] if linked else None


def save_track_template(
    profile_id: uuid.UUID,
    session: Session,
    track: Track,
    *,
    presentation: str,
    achievements: str,
) -> LetterTemplate | None:
    """Create or update the track's template; never a second one (F8, Data).

    The linked template follows its track: `lang`, `name` and `applies_when` are set from
    it on every save. None when the track is not this profile's.
    """
    if track.profile_id != profile_id:
        return None
    letter = track_template(profile_id, session, track)
    if letter is None:
        letter = LetterTemplate(profile_id=profile_id)
        session.add(letter)
    letter.track_id = track.id
    letter.lang = track.lang
    letter.name = track.name
    letter.applies_when = track.applies_when or ""
    letter.presentation = presentation.strip()
    letter.achievements = achievements.strip()
    session.flush()
    return letter


def use_template_for_track(
    profile_id: uuid.UUID,
    session: Session,
    template_id: str | uuid.UUID,
    track: Track,
) -> LetterTemplate | None:
    """Link this template to the track and unlink every other one (F8, "Usar esta").

    The chosen template takes the track's language, name and "when to use" like any
    linked one; the others keep their text and become unlinked, never deleted. None when
    the template or the track is not this profile's.
    """
    letter = get_letter(profile_id, session, template_id)
    if letter is None or track.profile_id != profile_id:
        return None
    for other in track_templates(profile_id, session, track):
        if other.id != letter.id:
            other.track_id = None
    letter.track_id = track.id
    letter.lang = track.lang
    letter.name = track.name
    letter.applies_when = track.applies_when or ""
    session.flush()
    return letter


def template_status(
    profile_id: uuid.UUID, session: Session, track: Track
) -> Literal["ready", "missing", "several", "other_lang"]:
    """What Puestos objetivo and Cartas say about a track's letter (F8).

    `missing`: no template, or the one in use has an empty presentation or achievements.
    `other_lang`: its language is not the track's (the track's language was changed).
    `several`: more than one template is linked, so the user has to choose.
    """
    linked = track_templates(profile_id, session, track)
    if not linked:
        return "missing"
    letter = linked[0]
    if not (letter.presentation or "").strip() or not (letter.achievements or "").strip():
        return "missing"
    if letter.lang != track.lang:
        return "other_lang"
    return "several" if len(linked) > 1 else "ready"


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


# The blocks "Autogenerar" may fill, in the order the form shows them. `voice_notes` is
# the user's own register and is never generated.
AUTOGENERATED_BLOCKS = ("header", "greeting", "closing", "sign_off")


def autogenerate_blocks(
    current: Mapping[str, str], lang: str, *, name: str, email: str
) -> dict[str, str]:
    """The common blocks with the empty ones filled by defaults (F8) — no model call.

    Fields the user already wrote are returned untouched. The defaults are the card's own
    language, not the interface's: the header from the profile's name and the account
    e-mail, a greeting and a closing that keep their placeholders, a sign-off with the name.
    """
    filled = {key: current.get(key, "") or "" for key in (*AUTOGENERATED_BLOCKS, "voice_notes")}
    for key in AUTOGENERATED_BLOCKS:
        if not filled[key].strip():
            filled[key] = t(f"letters.default.{key}", lang, name=name, email=email)
    return filled
