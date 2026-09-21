"""Tracks: the selection, its order, cloning, and the pages that edit it (PRD F4).

A track owns no content. These tests exist to hold that line: removing a bullet
from a track deletes nothing, editing one is visible from every track, and an id
belonging to another profile is dropped rather than followed.
"""

import pytest
from sqlalchemy import select

from src.bullets import create_bullet, get_bullet, list_bullets, update_bullet
from src.models import TrackBullet
from src.tracks import (
    clone_track,
    create_track,
    get_track,
    list_tracks,
    selection_sizes,
    set_track_active,
    set_track_bullets,
    track_bullets,
    update_track,
)


@pytest.fixture
def selection(session, career) -> list:
    """Three more bullets of Ana's own role, so an order has something to permute."""
    bullets = [
        create_bullet(
            career.first_profile.id,
            session,
            role_id=career.first_role.id,
            text_es=text,
            text_en=None,
        )
        for text in ("Primera línea", "Segunda línea", "Tercera línea")
    ]
    session.commit()
    return bullets


def positions_of(session, track_id) -> list[int]:
    rows = session.scalars(
        select(TrackBullet).where(TrackBullet.track_id == track_id).order_by(TrackBullet.position)
    )
    return [row.position for row in rows]


def test_cloning_a_track_copies_its_fields_and_the_selection_order(session, career, selection):
    profile_id = career.first_profile.id
    source = career.first_track
    chosen = [selection[2].id, career.first_bullet.id, selection[0].id]
    set_track_bullets(profile_id, session, source.id, chosen)

    clone = clone_track(profile_id, session, source.id, name="Analista de datos (copia)")

    assert clone is not None and clone.id != source.id
    assert clone.name == "Analista de datos (copia)"
    assert clone.applies_when == source.applies_when
    assert clone.lang == source.lang
    assert clone.headline == source.headline
    assert clone.target_seniority == source.target_seniority
    assert clone.active is True
    assert [bullet.id for bullet in track_bullets(profile_id, session, clone.id)] == chosen
    assert positions_of(session, clone.id) == [0, 1, 2]

    # Two selections, not one shared list: editing the clone leaves the source alone.
    set_track_bullets(profile_id, session, clone.id, [selection[1].id])

    assert [bullet.id for bullet in track_bullets(profile_id, session, source.id)] == chosen


def test_setting_the_selection_rewrites_the_order_and_drops_a_foreign_id(
    session, career, selection
):
    profile_id = career.first_profile.id
    track_id = career.first_track.id
    ids = [bullet.id for bullet in selection]

    set_track_bullets(profile_id, session, track_id, ids)
    assert [bullet.id for bullet in track_bullets(profile_id, session, track_id)] == ids
    assert positions_of(session, track_id) == [0, 1, 2]

    # Reordering rewrites `position` from scratch; nothing is appended to the old order.
    reversed_ids = list(reversed(ids))
    set_track_bullets(profile_id, session, track_id, reversed_ids)

    assert [bullet.id for bullet in track_bullets(profile_id, session, track_id)] == reversed_ids
    assert positions_of(session, track_id) == [0, 1, 2]

    # Another profile's bullet is dropped, not raised on, and not stored.
    kept = set_track_bullets(
        profile_id, session, track_id, [ids[0], career.second_bullet.id, ids[1]]
    )

    assert [bullet.id for bullet in kept] == [ids[0], ids[1]]
    assert [bullet.id for bullet in track_bullets(profile_id, session, track_id)] == [
        ids[0],
        ids[1],
    ]
    assert session.scalars(
        select(TrackBullet).where(
            TrackBullet.track_id == track_id, TrackBullet.bullet_id == career.second_bullet.id
        )
    ).all() == []


def test_removing_a_bullet_from_a_track_deletes_nothing(session, career, selection):
    profile_id = career.first_profile.id
    set_track_bullets(
        profile_id, session, career.first_track.id, [bullet.id for bullet in selection]
    )

    set_track_bullets(profile_id, session, career.first_track.id, [])

    assert track_bullets(profile_id, session, career.first_track.id) == []
    assert all(get_bullet(profile_id, session, bullet.id) is not None for bullet in selection)
    assert len(list_bullets(profile_id, session, active_only=True)) == len(selection) + 1


def test_editing_a_bullet_changes_it_in_every_track(session, career):
    """The track holds a reference; the text lives in one place."""
    profile_id = career.first_profile.id
    set_track_bullets(profile_id, session, career.first_track.id, [career.first_bullet.id])
    clone = clone_track(profile_id, session, career.first_track.id, name="Otra versión")

    update_bullet(
        profile_id,
        session,
        career.first_bullet.id,
        text_es="Reduje 30% el tiempo de reporte con Python y dbt",
        text_en=None,
        chips=["python"],
    )

    assert track_bullets(profile_id, session, career.first_track.id)[0].text_es.endswith("dbt")
    assert track_bullets(profile_id, session, clone.id)[0].text_es.endswith("dbt")


def test_a_track_can_be_deactivated_and_reactivated(session, career):
    profile_id = career.first_profile.id
    track_id = career.first_track.id

    set_track_active(profile_id, session, track_id, active=False)

    assert [track.id for track in list_tracks(profile_id, session, active_only=True)] == []
    assert [track.id for track in list_tracks(profile_id, session, active_only=False)] == [track_id]
    assert get_track(profile_id, session, track_id) is not None, "the row is kept"

    set_track_active(profile_id, session, track_id, active=True)

    assert [track.id for track in list_tracks(profile_id, session, active_only=True)] == [track_id]


def test_the_list_page_counts_come_from_the_selection(session, career, selection):
    profile_id = career.first_profile.id
    set_track_bullets(
        profile_id, session, career.first_track.id, [career.first_bullet.id, selection[0].id]
    )

    assert selection_sizes(profile_id, session) == {career.first_track.id: 2}
    assert selection_sizes(career.second_profile.id, session) == {career.second_track.id: 1}


def test_track_data_access_is_scoped_to_the_profile(session, career):
    other = career.second_profile.id
    mine = career.first_profile.id
    track_id = career.first_track.id

    assert get_track(other, session, track_id) is None
    assert update_track(other, session, track_id, name="Robada", applies_when="", lang="es") is None
    assert clone_track(other, session, track_id, name="Copia") is None
    assert set_track_active(other, session, track_id, active=False) is None
    assert set_track_bullets(other, session, track_id, [career.first_bullet.id]) is None
    assert track_bullets(other, session, track_id) == []
    assert [track.id for track in list_tracks(other, session, active_only=False)] == [
        career.second_track.id
    ]

    assert career.first_track.name == "Analista de datos"
    assert career.first_track.active is True
    assert [bullet.id for bullet in track_bullets(mine, session, track_id)] == [
        career.first_bullet.id
    ]


def test_a_new_track_starts_empty_and_keeps_the_fields_it_was_given(session, career):
    track = create_track(
        career.first_profile.id,
        session,
        name="  Data Engineer  ",
        applies_when="  Plataformas de datos  ",
        lang="en",
        target_seniority="senior",
        headline="Data Engineer",
        summary="Ingeniería de datos.",
    )

    assert track.name == "Data Engineer"
    assert track.applies_when == "Plataformas de datos"
    assert (track.lang, track.target_seniority, track.headline, track.summary) == (
        "en",
        "senior",
        "Data Engineer",
        "Ingeniería de datos.",
    )
    assert track_bullets(career.first_profile.id, session, track.id) == []

    cleared = update_track(
        career.first_profile.id,
        session,
        track.id,
        name="Data Engineer",
        applies_when="",
        lang="en",
        target_seniority="",
        headline="  ",
        summary=None,
    )

    assert (cleared.target_seniority, cleared.headline, cleared.summary) == (None, None, None)
