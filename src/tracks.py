"""Data access for tracks (PRD F4, F4.1).

A track owns no content: it references master bullets, pool summaries and pool
skills, so editing one updates it everywhere and removing it from a track deletes
nothing. `profile_id` comes first and ownership lives inside the query (F1), so
another profile's track is simply not found — never found and then rejected.

The headline slots and summary references are the whole CV the track presents (F4.1).
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.bullets import bullets_by_ids
from src.models import Bullet, Profile, Track, TrackBullet
from src.normalize.text import fold
from src.scoping import owned_row, owned_rows
from src.summaries import get_summary


def list_tracks(
    profile_id: uuid.UUID, session: Session, *, active_only: bool = True
) -> list[Track]:
    tracks = owned_rows(Track, session, profile_id, active_only=active_only)
    return sorted(tracks, key=lambda track: track.name)


def get_track(profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID) -> Track | None:
    return owned_row(Track, session, profile_id, track_id)


def create_track(
    profile_id: uuid.UUID,
    session: Session,
    *,
    name: str,
    applies_when: str = "",
    lang: str = "es",
    target_seniority: str | None = None,
    organisation_kind: str | None = None,
    specialisation: str | None = None,
    headline_es: str | None = None,
    headline_en: str | None = None,
    summary_es_id: uuid.UUID | str | None = None,
    summary_en_id: uuid.UUID | str | None = None,
    skills: Sequence[str] = (),
) -> Track:
    """A new track starts empty: the selection is the next screen, not a side effect.

    The summary slots reference the profile's pool (F4.1) and the skills are a
    selection of the profile's pool — a summary or skill belonging to nobody else
    can be referenced, and one that is not this profile's is dropped rather than
    followed, like a foreign bullet id.
    """
    track = Track(
        profile_id=profile_id,
        name=name.strip(),
        applies_when=applies_when.strip(),
        lang=(lang or "es")[:5],
        target_seniority=_clean(target_seniority),
        organisation_kind=_clean(organisation_kind),
        specialisation=_clean(specialisation),
        headline_es=_clean(headline_es),
        headline_en=_clean(headline_en),
        summary_es_id=_owned_summary_id(profile_id, session, summary_es_id),
        summary_en_id=_owned_summary_id(profile_id, session, summary_en_id),
        skills=_pool_skills(profile_id, session, skills),
    )
    session.add(track)
    session.flush()
    return track


def update_track(
    profile_id: uuid.UUID,
    session: Session,
    track_id: str | uuid.UUID,
    *,
    name: str,
    applies_when: str = "",
    lang: str = "es",
    target_seniority: str | None = None,
    organisation_kind: str | None = None,
    specialisation: str | None = None,
    headline_es: str | None = None,
    headline_en: str | None = None,
    summary_es_id: uuid.UUID | str | None = None,
    summary_en_id: uuid.UUID | str | None = None,
    skills: Sequence[str] = (),
    active: bool = True,
) -> Track | None:
    track = get_track(profile_id, session, track_id)
    if track is None:
        return None
    track.name = name.strip()
    track.applies_when = applies_when.strip()
    track.lang = (lang or "es")[:5]
    track.target_seniority = _clean(target_seniority)
    track.organisation_kind = _clean(organisation_kind)
    track.specialisation = _clean(specialisation)
    track.headline_es = _clean(headline_es)
    track.headline_en = _clean(headline_en)
    track.summary_es_id = _owned_summary_id(profile_id, session, summary_es_id)
    track.summary_en_id = _owned_summary_id(profile_id, session, summary_en_id)
    track.skills = _pool_skills(profile_id, session, skills)
    track.active = active
    session.flush()
    return track


def clone_track(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID, *, name: str
) -> Track | None:
    """Copy the fields and the selection, positions included. The source is untouched."""
    source = get_track(profile_id, session, track_id)
    if source is None:
        return None
    clone = create_track(
        profile_id,
        session,
        name=name,
        applies_when=source.applies_when,
        lang=source.lang,
        target_seniority=source.target_seniority,
        organisation_kind=source.organisation_kind,
        specialisation=source.specialisation,
        headline_es=source.headline_es,
        headline_en=source.headline_en,
        summary_es_id=source.summary_es_id,
        summary_en_id=source.summary_en_id,
        skills=source.skills,
    )
    members = session.scalars(
        select(TrackBullet)
        .where(TrackBullet.track_id == source.id)
        .order_by(TrackBullet.position)
    )
    for member in members:
        session.add(
            TrackBullet(track_id=clone.id, bullet_id=member.bullet_id, position=member.position)
        )
    session.flush()
    return clone


def set_track_skills(
    profile_id: uuid.UUID,
    session: Session,
    track_id: str | uuid.UUID,
    skills: Sequence[str],
) -> Track | None:
    """Replace the track's skill selection with this profile's pool canonicals (F7.3).

    F4.1's rule holds: a canonical that is not the profile's pool is dropped, not
    followed, so an accepted skills block cannot introduce a skill nobody owns.
    """
    track = get_track(profile_id, session, track_id)
    if track is None:
        return None
    track.skills = _pool_skills(profile_id, session, skills)
    session.flush()
    return track


def set_track_summary(
    profile_id: uuid.UUID,
    session: Session,
    track_id: str | uuid.UUID,
    *,
    lang: str,
    summary_id: uuid.UUID | str | None,
) -> Track | None:
    """Point one language slot at a pool row, or clear it (F4.1, F7.3).

    The slot references the pool, so accepting a summary for a track does not copy
    the text into the track: editing the pool row still changes every track that
    uses it.
    """
    track = get_track(profile_id, session, track_id)
    if track is None:
        return None
    owned = _owned_summary_id(profile_id, session, summary_id)
    if (lang or "es")[:5] == "en":
        track.summary_en_id = owned
    else:
        track.summary_es_id = owned
    session.flush()
    return track


def set_track_active(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID, *, active: bool
) -> Track | None:
    """Deactivate rather than delete: applications keep the track they were scored with."""
    track = get_track(profile_id, session, track_id)
    if track is None:
        return None
    track.active = active
    session.flush()
    return track


def track_bullets(
    profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID
) -> list[Bullet]:
    """The track's selection, in `position` order. Empty for a track we do not own."""
    track = get_track(profile_id, session, track_id)
    if track is None:
        return []
    stmt = (
        select(Bullet)
        .join(TrackBullet, TrackBullet.bullet_id == Bullet.id)
        .where(TrackBullet.track_id == track.id, Bullet.profile_id == profile_id)
        .order_by(TrackBullet.position)
    )
    return list(session.scalars(stmt))


def set_track_bullets(
    profile_id: uuid.UUID,
    session: Session,
    track_id: str | uuid.UUID,
    bullet_ids: Sequence[uuid.UUID],
) -> list[Bullet] | None:
    """Replace the selection, writing `position` as the index of each id.

    Ids that are not this profile's bullets — another profile's, or ids that no
    longer exist — are dropped rather than raising: the picker posts ids, and a
    stale form must not turn into a 500. None means the track is not ours.
    """
    track = get_track(profile_id, session, track_id)
    if track is None:
        return None
    kept = bullets_by_ids(profile_id, session, bullet_ids)
    session.execute(delete(TrackBullet).where(TrackBullet.track_id == track.id))
    for position, bullet in enumerate(kept):
        session.add(TrackBullet(track_id=track.id, bullet_id=bullet.id, position=position))
    session.flush()
    return kept


def selection_sizes(profile_id: uuid.UUID, session: Session) -> dict[uuid.UUID, int]:
    """Bullets per track, in one query, for the list page's counts."""
    stmt = (
        select(TrackBullet.track_id, func.count())
        .join(Track, Track.id == TrackBullet.track_id)
        .where(Track.profile_id == profile_id)
        .group_by(TrackBullet.track_id)
    )
    return {track_id: count for track_id, count in session.execute(stmt)}


def _clean(value: str | None) -> str | None:
    """A cleared form field arrives as an empty string; the columns mean NULL by unset."""
    return (value or "").strip() or None


def _owned_summary_id(
    profile_id: uuid.UUID, session: Session, value: uuid.UUID | str | None
) -> uuid.UUID | None:
    """A summary slot points into this profile's pool, or it points nowhere.

    An id from a form is as untrusted as one from a URL: another profile's row is
    dropped rather than followed, exactly like a foreign bullet id in the picker.
    """
    if not value:
        return None
    entry = get_summary(profile_id, session, value)
    return entry.id if entry is not None else None


def _pool_skills(
    profile_id: uuid.UUID, session: Session, skills: Sequence[str]
) -> list[str]:
    """The skill selection is a subset of the profile's pool (F4.1), and nothing else.

    A skill no upload or manual entry ever listed cannot be added to a track here —
    the pool is the ceiling, so the form's checkbox list and the stored selection
    cannot drift apart.
    """
    profile = session.get(Profile, profile_id)
    if profile is None:
        return []
    pool = {fold(skill): skill for skill in profile.skills}
    kept: list[str] = []
    for skill in skills:
        canonical = pool.get(fold(skill or ""))
        if canonical is not None and canonical not in kept:
            kept.append(canonical)
    return kept
