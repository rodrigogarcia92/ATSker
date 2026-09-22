"""Data access for tracks (PRD F4).

A track owns no content: it references master bullets, so editing one updates it
everywhere and removing it from a track deletes nothing. `profile_id` comes first
and ownership lives inside the query (F1), so another profile's track is simply
not found — never found and then rejected.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.bullets import bullets_by_ids
from src.models import Bullet, Track, TrackBullet
from src.scoping import owned_row, owned_rows


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
    headline: str | None = None,
    summary: str | None = None,
) -> Track:
    """A new track starts empty: the selection is the next screen, not a side effect."""
    track = Track(
        profile_id=profile_id,
        name=name.strip(),
        applies_when=applies_when.strip(),
        lang=(lang or "es")[:5],
        target_seniority=_clean(target_seniority),
        organisation_kind=_clean(organisation_kind),
        specialisation=_clean(specialisation),
        headline=_clean(headline),
        summary=_clean(summary),
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
    headline: str | None = None,
    summary: str | None = None,
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
    track.headline = _clean(headline)
    track.summary = _clean(summary)
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
        headline=source.headline,
        summary=source.summary,
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
