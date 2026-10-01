"""Permanent deletion between the two users (PRD F2.8).

What is asserted here is §F2.8's table itself: every confirmation number is what
the delete then removes (and the things it names as kept really stay), another
profile's rows are 404 and untouched, "only this CV contributed" never deletes a
bullet whose provenance is unknown, and Eliminar todo redacts that profile's
personal ledger answers while the login survives.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select

from src.applications import create_application
from src.deletion import (
    delete_bullet,
    delete_resume,
    impact_application,
    impact_bullet,
    impact_letter_template,
    impact_resume,
    impact_role,
    impact_skill,
    impact_story,
    impact_summary,
    impact_track,
)
from src.extract.boolean import PURPOSE as BOOLEAN_QUERIES
from src.extract.gaps import PURPOSE as GAP_INTERPRET
from src.extract.grading import PURPOSE as EVIDENCE_GRADE
from src.extract.jd import PURPOSE as JD_EXTRACT
from src.extract.resume import PURPOSE as RESUME_EXTRACT
from src.extract.stories import PURPOSE as STORY_SUGGEST
from src.models import (
    Application,
    Bullet,
    BulletRevision,
    LetterTemplate,
    LlmCall,
    Profile,
    Resume,
    Role,
    Skill,
    Story,
    StoryBullet,
    Summary,
    Track,
    TrackBullet,
    User,
)
from src.resumes import create_resume
from tests.conftest import login
from tests.unit.test_analysis import w3_report


def _application(profile_id, session, *, title: str = "Puesto", report: dict | None = None):
    return create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report=report if report is not None else {},
        weights_version="w3",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title=title,
    )


def _resume(profile_id, session, *, name: str = "cv.pdf") -> Resume:
    return create_resume(profile_id, session, filename=name, data=b"%PDF", sha256="a" * 64)


def _ledger(session, profile_id, purpose: str, **overrides) -> LlmCall:
    values = {
        "purpose": purpose,
        "prompt_version": "v1",
        "model": "test/model-v1",
        "input_hash": uuid.uuid4().hex,
        "response_json": {"answer": "personal content"},
        "prompt_tokens": 7,
        "completion_tokens": 3,
        "cost_usd": Decimal("0.001000"),
        "profile_id": profile_id,
    }
    values.update(overrides)
    row = LlmCall(**values)
    session.add(row)
    return row


def _exists(session, model, row_id) -> bool:
    """Query-based existence: `session.get` raises on an expired deleted instance."""
    return session.scalars(select(model).where(model.id == row_id)).first() is not None


def test_user_a_gets_404_on_every_delete_route_and_bs_rows_are_untouched(client, session, career):
    """F1's isolation (404, never 403) for every Eliminar the F2.8 table adds."""
    login(client, career.first.email)
    theirs_application = _application(career.second_profile.id, session, title="De Bea")
    theirs_resume = _resume(career.second_profile.id, session, name="bea.pdf")
    # The shared vocabulary already knows "python"; only Bea's pool and tracks list it.
    career.first_profile.skills = []
    career.first_track.skills = []
    career.second_profile.skills = ["python"]
    career.second_track.skills = ["python"]
    session.commit()

    targets = [
        f"/roles/{career.second_role.id}/delete",
        f"/bullets/{career.second_bullet.id}/delete",
        f"/tracks/{career.second_track.id}/delete",
        f"/summaries/{career.second_summary.id}/delete",
        f"/stories/{career.second_story.id}/delete",
        f"/letters/{career.second_letter.id}/delete",
        f"/applications/{theirs_application.id}/delete",
        f"/import/{theirs_resume.id}/delete",
    ]
    for path in targets:
        assert client.get(path).status_code == 404, path
        assert client.post(path).status_code == 404, path
    assert client.get("/roles/not-a-uuid/delete").status_code == 404

    # A skill of Bea's pool is Bea's: it is not in Ana's, so it is not found.
    assert client.get("/profile/skills/delete", params={"skill": "python"}).status_code == 404
    refused = client.post("/profile/skills/delete", data={"skill": "python"})
    assert refused.status_code == 404

    assert session.get(Role, career.second_role.id) is not None
    assert session.get(Bullet, career.second_bullet.id) is not None
    assert session.get(Track, career.second_track.id) is not None
    assert session.get(Summary, career.second_summary.id) is not None
    assert session.get(Story, career.second_story.id) is not None
    assert session.get(Application, theirs_application.id) is not None
    assert session.get(Resume, theirs_resume.id) is not None
    assert career.second_profile.skills == ["python"] and career.second_track.skills == ["python"]


def test_role_delete_numbers_match_and_stories_survive_cleared(client, session, career):
    login(client, career.first.email)
    role = Role(profile_id=career.first_profile.id, employer="Banco", title="Analista")
    session.add(role)
    session.flush()
    first = Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Uno")
    second = Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Dos")
    session.add_all([first, second])
    session.flush()
    session.add(BulletRevision(bullet_id=first.id, text_es="Uno (v1)"))
    story = Story(profile_id=career.first_profile.id, role_id=role.id, title="T", body="B")
    session.add(story)
    session.commit()
    role_id, first_id, second_id = role.id, first.id, second.id

    numbers = impact_role(career.first_profile.id, session, role_id)
    posted = client.post(f"/roles/{role.id}/delete", follow_redirects=False)
    assert posted.status_code == 303
    session.expire_all()

    removed = {"roles": 1, "bullets": 2, "revisions": 1}
    assert {key: numbers[key] for key in removed} == removed, "the screen numbers are the removal"
    assert numbers["stories"] == 1
    assert not _exists(session, Role, role_id)
    assert not _exists(session, Bullet, first_id) and not _exists(session, Bullet, second_id)
    remaining = session.scalars(
        select(BulletRevision).where(BulletRevision.bullet_id == first_id)
    ).all()
    assert remaining == []
    assert session.get(Story, story.id) is not None and story.role_id is None


def test_bullet_delete_numbers_match_and_the_analyses_keep_their_copy(client, session, career):
    login(client, career.first.email)
    role = Role(profile_id=career.first_profile.id, employer="Banco", title="Analista")
    session.add(role)
    session.flush()
    bullet = Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Texto citado")
    session.add(bullet)
    session.flush()
    other = Track(profile_id=career.first_profile.id, name="Otra pista")
    session.add_all([other])
    session.flush()
    session.add_all(
        [
            TrackBullet(track_id=career.first_track.id, bullet_id=bullet.id, position=0),
            TrackBullet(track_id=other.id, bullet_id=bullet.id, position=0),
            StoryBullet(story_id=career.first_story.id, bullet_id=bullet.id),
            BulletRevision(bullet_id=bullet.id, text_es="Antes"),
            BulletRevision(bullet_id=bullet.id, text_es="Antes 2"),
        ]
    )
    application = _application(
        career.first_profile.id,
        session,
        report={"grades": [{"bullet_id": str(bullet.id), "bullet_text": "Texto citado"}]},
    )
    session.commit()
    bullet_id = bullet.id

    numbers = impact_bullet(career.first_profile.id, session, bullet_id)
    posted = client.post(f"/bullets/{bullet.id}/delete", follow_redirects=False)
    assert posted.status_code == 303
    session.expire_all()

    removed = {"bullets": 1, "tracks": 2, "story_links": 1, "revisions": 2}
    assert {key: numbers[key] for key in removed} == removed
    assert numbers["analyses"] == 1, "cited by one analysis, which keeps its copy"
    assert not _exists(session, Bullet, bullet_id)
    track_links = session.scalars(
        select(TrackBullet).where(TrackBullet.bullet_id == bullet_id)
    ).all()
    story_links = session.scalars(
        select(StoryBullet).where(StoryBullet.bullet_id == bullet_id)
    ).all()
    assert track_links == [] and story_links == []
    survivor = session.get(Application, application.id)
    assert survivor is not None
    assert survivor.report["grades"][0]["bullet_text"] == "Texto citado"


def test_track_summary_story_letter_and_application_numbers_match_the_post(client, session, career):
    login(client, career.first.email)
    summary = Summary(profile_id=career.first_profile.id, lang="es", text="Resumen")
    session.add(summary)
    session.flush()
    career.first_track.summary_es_id = summary.id
    career.first_track.name = "Pista"
    application = _application(career.first_profile.id, session)
    session.commit()
    track_id = career.first_track.id
    summary_id = summary.id
    story_id = career.first_story.id
    letter_id = career.first_letter.id
    application_id = application.id
    # The fixture's own selection and story link are what the numbers must count.
    selection = len(
        session.scalars(select(TrackBullet).where(TrackBullet.track_id == track_id)).all()
    )
    links = len(session.scalars(select(StoryBullet).where(StoryBullet.story_id == story_id)).all())

    track_numbers = impact_track(career.first_profile.id, session, track_id)
    summary_numbers = impact_summary(career.first_profile.id, session, summary_id)
    story_numbers = impact_story(career.first_profile.id, session, story_id)
    letter_numbers = impact_letter_template(career.first_profile.id, session, letter_id)
    application_numbers = impact_application(career.first_profile.id, session, application_id)

    for path in (
        f"/tracks/{track_id}/delete",
        f"/summaries/{summary_id}/delete",
        f"/stories/{story_id}/delete",
        f"/letters/{letter_id}/delete",
        f"/applications/{application_id}/delete",
    ):
        assert client.post(path, follow_redirects=False).status_code == 303, path
    session.expire_all()

    assert track_numbers["tracks"] == 1 and track_numbers["selection"] == selection
    assert summary_numbers == {"summaries": 1, "tracks": 1}
    assert story_numbers == {"stories": 1, "links": links}
    assert letter_numbers == {"letter_templates": 1}
    assert application_numbers == {"applications": 1, "application_attempts": 0}
    assert not _exists(session, Track, track_id)
    assert not _exists(session, Summary, summary_id)
    assert not _exists(session, Story, story_id)
    story_links = session.scalars(
        select(StoryBullet).where(StoryBullet.story_id == story_id)
    ).all()
    assert story_links == []
    assert not _exists(session, LetterTemplate, letter_id)
    assert not _exists(session, Application, application_id)
    assert _exists(session, Bullet, career.first_bullet.id), "bullets are kept"
    assert career.first_bullet.active is True


def test_cv_delete_keeps_its_bullets_unless_ticked_and_never_touches_unknown_provenance(
    client, session, career
):
    login(client, career.first.email)
    first_cv = _resume(career.first_profile.id, session, name="uno.pdf")
    second_cv = _resume(career.first_profile.id, session, name="dos.pdf")
    session.flush()
    role = Role(profile_id=career.first_profile.id, employer="Banco", title="Analista")
    session.add(role)
    session.flush()
    from_first = Bullet(
        profile_id=career.first_profile.id,
        role_id=role.id,
        text_es="Del primer CV",
        source_resume_id=first_cv.id,
    )
    from_second = Bullet(
        profile_id=career.first_profile.id,
        role_id=role.id,
        text_es="Del segundo CV",
        source_resume_id=second_cv.id,
    )
    unknown = Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Sin origen")
    session.add_all([from_first, from_second, unknown])
    session.commit()
    first_cv_id, second_cv_id = first_cv.id, second_cv.id
    from_first_id, from_second_id, unknown_id = from_first.id, from_second.id, unknown.id

    numbers = impact_resume(career.first_profile.id, session, first_cv_id)
    # Two unknown: "Sin origen" and the fixture's own bullet, which no CV is proven
    # to have contributed either.
    assert numbers == {"resumes": 1, "bullets": 1, "bullets_unknown": 2}

    # Without the tick: the CV goes and every bullet stays.
    assert client.post(f"/import/{first_cv_id}/delete", follow_redirects=False).status_code == 303
    session.expire_all()
    assert not _exists(session, Resume, first_cv_id)
    assert _exists(session, Bullet, from_first_id)
    assert from_first.source_resume_id is None, "the pointer goes with the document"

    # With the tick: only the bullets this CV is proven to have contributed.
    posted = client.post(
        f"/import/{second_cv_id}/delete",
        data={"delete_bullets": "on"},
        follow_redirects=False,
    )
    assert posted.status_code == 303
    session.expire_all()
    assert not _exists(session, Bullet, from_second_id)
    assert _exists(session, Bullet, unknown_id), "unknown provenance is never deleted"
    assert delete_resume(career.first_profile.id, session, second_cv_id) is None
    assert impact_resume(career.first_profile.id, session, second_cv_id) is None


def test_skill_delete_clears_the_pool_and_every_track_and_keeps_the_vocabulary(
    client, session, career
):
    login(client, career.first.email)
    second = Track(profile_id=career.first_profile.id, name="Segunda pista")
    session.add(second)
    session.flush()
    career.first_profile.skills = ["python", "machine learning"]
    career.first_track.skills = ["python"]
    second.skills = ["python", "machine learning"]
    session.commit()

    numbers = impact_skill(career.first_profile.id, session, "python")
    assert numbers == {"pool": 1, "tracks": 2}

    posted = client.post("/profile/skills/delete", data={"skill": "python"}, follow_redirects=False)
    assert posted.status_code == 303
    session.expire_all()

    assert career.first_profile.skills == ["machine learning"]
    assert career.first_track.skills == [] and second.skills == ["machine learning"]
    vocabulary = session.scalars(select(Skill).where(Skill.canonical == "python")).one()
    assert vocabulary.aliases == ["python", "py"], "the shared vocabulary is nobody's to delete"


def test_eliminar_todo_needs_the_word_then_wipes_the_profile_and_redacts_the_ledger(
    client, session, career
):
    login(client, career.first.email)
    career.first_profile.headline = "Headline"
    career.first_profile.summary = "Resumen"
    career.first_profile.skills = ["python"]
    career.first_profile.standing_risks = ["Riesgo"]
    role = Role(profile_id=career.first_profile.id, employer="Banco", title="Analista")
    session.add(role)
    session.flush()
    session.add(Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Bala"))
    resume = _resume(career.first_profile.id, session)
    summary = Summary(profile_id=career.first_profile.id, lang="es", text="Resumen")
    application = _application(career.first_profile.id, session)
    session.add_all([summary])
    session.flush()
    personal = _ledger(session, career.first_profile.id, RESUME_EXTRACT)
    grading_row = _ledger(session, career.first_profile.id, EVIDENCE_GRADE)
    gap_row = _ledger(session, career.first_profile.id, GAP_INTERPRET)
    story_row = _ledger(session, career.first_profile.id, STORY_SUGGEST)
    jd_row = _ledger(session, career.first_profile.id, JD_EXTRACT)
    boolean_row = _ledger(session, career.first_profile.id, BOOLEAN_QUERIES)
    unattributable = _ledger(session, None, RESUME_EXTRACT)
    theirs = _ledger(session, career.second_profile.id, RESUME_EXTRACT)
    session.commit()
    row_ids = [(type(row), row.id) for row in (role, resume, summary, application)]

    # The typed word is the gate: no word, no deletion.
    assert client.post("/profile/delete", data={}, follow_redirects=False).status_code == 422
    assert client.post(
        "/profile/delete", data={"confirm_word": "eliminar"}, follow_redirects=False
    ).status_code == 422
    assert session.get(Role, role.id) is not None

    posted = client.post(
        "/profile/delete", data={"confirm_word": "ELIMINAR"}, follow_redirects=False
    )
    assert posted.status_code == 303
    session.expire_all()

    assert session.get(User, career.first.id) is not None, "the login stays"
    profile = session.get(Profile, career.first_profile.id)
    assert profile is not None, "the profile row stays, blanked"
    assert profile.headline is None and profile.summary is None
    assert profile.skills == [] and profile.standing_risks == []
    for model, row_id in row_ids:
        assert not _exists(session, model, row_id)
    gone = (
        session.scalars(select(Bullet).where(Bullet.profile_id == career.first_profile.id)).all(),
        session.scalars(select(Track).where(Track.profile_id == career.first_profile.id)).all(),
        session.scalars(select(Story).where(Story.profile_id == career.first_profile.id)).all(),
    )
    assert gone == ([], [], [])

    for row in (personal, grading_row, gap_row, story_row):
        fresh = session.get(LlmCall, row.id)
        assert fresh.response_json == {} and fresh.degenerate is True
        assert fresh.prompt_tokens == 7 and fresh.completion_tokens == 3
        assert fresh.cost_usd == Decimal("0.001000"), "tokens and cost are kept"
    for row in (jd_row, boolean_row):
        fresh = session.get(LlmCall, row.id)
        assert fresh.response_json == {"answer": "personal content"}, "not personal, kept whole"
        assert fresh.degenerate is False
    assert session.get(LlmCall, unattributable.id).response_json == {"answer": "personal content"}
    fresh_theirs = session.get(LlmCall, theirs.id)
    assert fresh_theirs.response_json == {"answer": "personal content"}, "another profile's rows"


def test_a_stored_report_renders_its_snapshot_without_a_link_after_the_bullet_is_deleted(
    client, session, career
):
    """F5.4/F2.8: the report already snapshots what it cites; a deleted citation
    renders from that snapshot, and nothing links to the row that is gone."""
    login(client, career.first.email)
    role = Role(profile_id=career.first_profile.id, employer="Banco", title="Analista")
    session.add(role)
    session.flush()
    bullet = Bullet(profile_id=career.first_profile.id, role_id=role.id, text_es="Texto citado")
    session.add(bullet)
    session.flush()
    bullet_id = bullet.id
    report = w3_report()
    report["grades"][0]["bullet_id"] = str(bullet_id)
    report["grades"][0]["bullet_text"] = "Texto citado"
    application = _application(career.first_profile.id, session, report=report)
    session.commit()

    assert delete_bullet(career.first_profile.id, session, bullet_id) == {
        "bullets": 1,
        "tracks": 0,
        "story_links": 0,
        "revisions": 0,
    }
    session.commit()
    session.expire_all()
    assert not _exists(session, Bullet, bullet_id)

    page = client.get(f"/applications/{application.id}")
    assert page.status_code == 200
    assert "Texto citado" in page.text, "the snapshot renders"
    assert f"/bullets/{bullet_id}" not in page.text, "and nothing links to the deleted row"
