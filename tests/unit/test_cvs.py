"""CVs of a track (PRD F11.1): which files an analysis may read, newest first."""

import uuid

from src.resumes import latest_cv, resolve_cv, track_cvs
from src.tracks import create_track
from tests.unit.cv_support import draft_dict, make_cv


def test_a_track_lists_its_merged_active_cvs_newest_first(session, career):
    profile, track = career.first_profile, career.first_track
    old = make_cv(session, profile, track, name="old.docx", age_days=30)
    new = make_cv(session, profile, track, name="new.docx", age_days=1)
    mid = make_cv(session, profile, track, name="mid.docx", age_days=10)

    assert [cv.id for cv in track_cvs(profile.id, session, track.id)] == [new.id, mid.id, old.id]
    assert latest_cv(profile.id, session, track.id).id == new.id


def test_a_cv_that_is_pending_hidden_or_without_a_draft_is_not_one(session, career):
    profile, track = career.first_profile, career.first_track
    good = make_cv(session, profile, track, name="good.docx", age_days=5)
    make_cv(session, profile, track, name="pending.docx", merged=False)
    make_cv(session, profile, track, name="hidden.docx", active=False)
    blank = make_cv(session, profile, track, name="blank.docx")
    blank.draft = None
    session.commit()

    assert [cv.id for cv in track_cvs(profile.id, session, track.id)] == [good.id]


def test_a_track_without_a_cv_has_no_latest(session, career):
    assert track_cvs(career.first_profile.id, session, career.first_track.id) == []
    assert latest_cv(career.first_profile.id, session, career.first_track.id) is None
    assert resolve_cv(career.first_profile.id, session, career.first_track.id, "latest") is None


def test_ties_are_broken_the_same_way_every_time(session, career):
    profile, track = career.first_profile, career.first_track
    a = make_cv(session, profile, track, name="a.docx", age_days=3)
    b = make_cv(session, profile, track, name="b.docx", age_days=3)

    first = [cv.id for cv in track_cvs(profile.id, session, track.id)]
    again = [cv.id for cv in track_cvs(profile.id, session, track.id)]

    assert first == again
    assert set(first) == {a.id, b.id}


def test_latest_resolves_to_the_newest_cv_now(session, career):
    profile, track = career.first_profile, career.first_track
    older = make_cv(session, profile, track, name="a.docx", age_days=9)
    assert resolve_cv(profile.id, session, track.id, "latest").id == older.id

    newer = make_cv(session, profile, track, name="b.docx", age_days=1)

    assert resolve_cv(profile.id, session, track.id, "latest").id == newer.id
    assert resolve_cv(profile.id, session, track.id, "").id == newer.id
    assert resolve_cv(profile.id, session, track.id, None).id == newer.id


def test_an_explicit_id_resolves_only_inside_the_track(session, career):
    profile, track = career.first_profile, career.first_track
    other_track = create_track(
        profile.id, session, name="BI Analyst", applies_when="BI", lang="en"
    )
    mine = make_cv(session, profile, track, name="mine.docx", age_days=4)
    elsewhere = make_cv(session, profile, other_track, name="bi.docx", age_days=2)
    session.commit()

    assert resolve_cv(profile.id, session, track.id, str(mine.id)).id == mine.id
    assert resolve_cv(profile.id, session, track.id, str(elsewhere.id)) is None, "other track"
    assert resolve_cv(profile.id, session, other_track.id, str(elsewhere.id)).id == elsewhere.id
    assert resolve_cv(profile.id, session, track.id, str(uuid.uuid4())) is None
    assert resolve_cv(profile.id, session, track.id, "not-an-id") is None


def test_another_profiles_cv_and_track_are_not_found(session, career):
    theirs = make_cv(
        session, career.second_profile, career.second_track, name="theirs.docx", draft=draft_dict()
    )

    assert track_cvs(career.first_profile.id, session, career.second_track.id) == []
    assert (
        resolve_cv(career.first_profile.id, session, career.first_track.id, str(theirs.id))
        is None
    )
    assert (
        resolve_cv(career.first_profile.id, session, career.second_track.id, str(theirs.id))
        is None
    )
    assert latest_cv(career.second_profile.id, session, career.second_track.id).id == theirs.id
