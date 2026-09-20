"""Data access for tracks (PRD F4).

N2 builds creation, cloning and bullet selection. N1 needs two things only: the
upload form tags a résumé with an intended track (F2.1), and the merge screen reads
the drafts a track's bullets came from.
"""

import uuid

from sqlalchemy.orm import Session

from src.models import Track
from src.scoping import owned_row, owned_rows


def list_tracks(
    profile_id: uuid.UUID, session: Session, *, active_only: bool = True
) -> list[Track]:
    tracks = owned_rows(Track, session, profile_id, active_only=active_only)
    return sorted(tracks, key=lambda track: track.name)


def get_track(profile_id: uuid.UUID, session: Session, track_id: str | uuid.UUID) -> Track | None:
    return owned_row(Track, session, profile_id, track_id)