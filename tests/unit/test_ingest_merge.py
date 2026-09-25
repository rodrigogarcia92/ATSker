"""The F2.5 merge: diff labels, history, and the rule that nothing overwrites silently.

The acceptance path is here: a first upload creates, a second upload of the same
content diffs as unchanged and duplicates nothing, and a changed bullet keeps the
text it had.
"""

import hashlib
from dataclasses import replace

from sqlalchemy import select

from src.bullets import create_bullet, get_bullet, list_bullets, set_bullet_active
from src.certifications import list_certifications
from src.education import list_educations
from src.ingest.draft import DraftBullet, DraftCertification, DraftEducation, DraftRole, ResumeDraft
from src.ingest.merge import MergeResult, Selections, apply_merge, diff_draft
from src.models import BulletRevision, Resume, Summary, TrackBullet
from src.resumes import create_resume
from src.roles import list_roles
from src.summaries import list_summaries
from src.tracks import get_track, set_track_bullets, track_bullets


def make_resume(
    session, profile_id, draft: ResumeDraft, name: str = "cv", track_id=None
) -> Resume:
    return create_resume(
        profile_id,
        session,
        filename=f"{name}.docx",
        data=b"bytes",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        track_id=track_id,
        gate={},
        draft=draft.model_dump(mode="json"),
    )


def full_draft(bullet_text: str = "Modelé el riesgo de crédito con Python") -> ResumeDraft:
    return ResumeDraft(
        language="es",
        headline="Analista de datos",
        summary="Cinco años automatizando reportes.",
        skills=["python"],
        roles=[
            DraftRole(
                employer="Globex",
                title="Data Scientist",
                start_date="2021-01",
                bullets=[DraftBullet(text=bullet_text, chips=["python"])],
            )
        ],
        educations=[
            DraftEducation(
                institution="Universidad Nacional de Ingeniería",
                award="Bachiller en Ingeniería de Sistemas",
                end_date="2019",
            )
        ],
        certifications=[
            DraftCertification(name="Scrum Master", issuer="Scrum Alliance", issued_date="2020-03")
        ],
    )


def select_all(plan) -> Selections:
    return Selections(
        roles=frozenset(range(len(plan.roles))),
        bullets=frozenset(
            (index, bullet)
            for index, role in enumerate(plan.roles)
            for bullet in range(len(role.bullets))
        ),
        educations=frozenset(range(len(plan.educations))),
        certifications=frozenset(range(len(plan.certifications))),
        skills=frozenset(range(len(plan.skills))),
    )


def test_a_headline_longer_than_the_column_is_not_set_and_the_result_says_so(session, career):
    """The column is 200 and a cut sentence says something else: the 210-character
    headline is not written, the merge still lands everything else, and the note
    says why in the result.
    """
    profile_id = career.first_profile.id
    draft = full_draft().model_copy(update={"headline": "x" * 210})
    resume = make_resume(session, profile_id, draft)

    plan = diff_draft(profile_id, session, draft)
    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    track = get_track(profile_id, session, result.track_id)
    assert track.headline_es is None, "headline stays unset"
    assert replace(result, track_id=None) == MergeResult(
        roles_created=1,
        bullets_created=1,
        educations_created=1,
        certifications_created=1,
        skills_added=1,
        track_skills_added=1,
        track_summary_filled=True,
        track_created=True,
        headline_not_set=(210, 200),
    )
    assert result.note == "headline not set: 210 characters, limit 200"


def test_a_long_headline_leaves_an_existing_track_headline_untouched(session, career):
    """The track keeps the headline it has; the note explains the draft's absence."""
    profile_id = career.first_profile.id
    first_draft = full_draft()
    first = make_resume(session, profile_id, first_draft, "first")
    plan = diff_draft(profile_id, session, first_draft)
    created = apply_merge(
        profile_id,
        session,
        resume_id=first.id,
        draft=first_draft,
        plan=plan,
        selections=select_all(plan),
        track_name="Puesto",
    )

    long_draft = full_draft().model_copy(update={"headline": "y" * 210})
    second = make_resume(session, profile_id, long_draft, "second", track_id=created.track_id)
    plan = diff_draft(profile_id, session, long_draft)
    result = apply_merge(
        profile_id,
        session,
        resume_id=second.id,
        draft=long_draft,
        plan=plan,
        selections=select_all(plan),
    )

    track = get_track(profile_id, session, created.track_id)
    assert track.headline_es == "Analista de datos", "the track keeps the headline it has"
    assert result.track_headline_kept is True
    assert result.headline_not_set == (210, 200)
    assert result.note is not None


def test_a_headline_within_the_limit_is_written_as_before(session, career):
    profile_id = career.first_profile.id
    draft = full_draft().model_copy(update={"headline": "t" * 150})
    resume = make_resume(session, profile_id, draft)

    plan = diff_draft(profile_id, session, draft)
    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    track = get_track(profile_id, session, result.track_id)
    assert track.headline_es == "t" * 150
    assert result.track_headline_filled is True
    assert result.headline_not_set is None
    assert result.note is None


def test_a_first_upload_diffs_as_new_and_merges_everything(session, career):
    profile_id = career.first_profile.id
    draft = full_draft()
    resume = make_resume(session, profile_id, draft)

    plan = diff_draft(profile_id, session, draft)
    assert [role.label for role in plan.roles] == ["new"]
    assert [bullet.label for role in plan.roles for bullet in role.bullets] == ["new"]
    assert [entry.label for entry in plan.educations] == ["new"]
    assert [entry.label for entry in plan.certifications] == ["new"]
    assert [entry.label for entry in plan.skills] == ["new"]
    assert plan.label_counts() == {"new": 5, "changed": 0, "unchanged": 0}

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    assert replace(result, track_id=None) == MergeResult(
        roles_created=1,
        bullets_created=1,
        educations_created=1,
        certifications_created=1,
        skills_added=1,
        track_skills_added=1,
        track_headline_filled=True,
        track_summary_filled=True,
        track_created=True,
    )
    roles = list_roles(profile_id, session, active_only=False)
    assert "Globex" in {role.employer for role in roles}
    created = next(role for role in roles if role.employer == "Globex")
    bullets = list_bullets(profile_id, session, active_only=True, role_id=created.id)
    assert [bullet.text_es for bullet in bullets] == ["Modelé el riesgo de crédito con Python"]
    assert bullets[0].skills == ["python"]
    assert [entry.institution for entry in list_educations(profile_id, session)] == [
        "Universidad Nacional de Ingeniería"
    ]
    assert [entry.name for entry in list_certifications(profile_id, session)] == ["Scrum Master"]
    assert career.first_profile.skills == ["python"]
    assert resume.merged_at is not None


def test_a_second_upload_of_the_same_draft_is_unchanged_and_duplicates_nothing(session, career):
    profile_id = career.first_profile.id
    draft = full_draft()
    first = make_resume(session, profile_id, draft, "first")
    first_plan = diff_draft(profile_id, session, draft)
    apply_merge(
        profile_id,
        session,
        resume_id=first.id,
        draft=draft,
        plan=first_plan,
        selections=select_all(first_plan),
    )
    counts_before = (
        len(list_roles(profile_id, session, active_only=False)),
        len(list_bullets(profile_id, session, active_only=False)),
        len(list_educations(profile_id, session)),
        len(list_certifications(profile_id, session)),
        len(list_summaries(profile_id, session)),
    )

    second = make_resume(session, profile_id, draft, "second")
    plan = diff_draft(profile_id, session, draft)

    assert [role.label for role in plan.roles] == ["unchanged"]
    assert [bullet.label for role in plan.roles for bullet in role.bullets] == ["unchanged"]
    assert [entry.label for entry in plan.educations] == ["unchanged"]
    assert [entry.label for entry in plan.certifications] == ["unchanged"]
    assert [entry.label for entry in plan.skills] == ["unchanged"]

    result = apply_merge(
        profile_id,
        session,
        resume_id=second.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    assert replace(result, track_id=None) == MergeResult(
        track_skills_added=1,
        track_headline_filled=True,
        track_summary_filled=True,
        track_created=True,
    ), "unchanged candidates write nothing; the document still lands in its own track"
    assert counts_before == (
        len(list_roles(profile_id, session, active_only=False)),
        len(list_bullets(profile_id, session, active_only=False)),
        len(list_educations(profile_id, session)),
        len(list_certifications(profile_id, session)),
        len(list_summaries(profile_id, session)),
    )


def test_a_reworded_bullet_is_changed_and_keeps_the_old_text(session, career):
    profile_id = career.first_profile.id
    original = career.first_bullet
    old_text = original.text_es
    draft = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[
                    DraftBullet(
                        text="Reduje el tiempo de reporte un 30% con Python",
                        chips=["python"],
                    )
                ],
            )
        ],
    )
    resume = make_resume(session, profile_id, draft)

    plan = diff_draft(profile_id, session, draft)
    candidate = plan.roles[0].bullets[0]
    assert plan.roles[0].label == "unchanged"
    assert candidate.label == "changed"
    assert candidate.old_text == old_text

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    assert result.bullets_updated == 1
    assert result.bullets_created == 0
    updated = get_bullet(profile_id, session, original.id)
    assert updated.text_es == "Reduje el tiempo de reporte un 30% con Python"
    revisions = session.query(BulletRevision).all()
    assert [revision.text_es for revision in revisions] == [old_text]
    assert revisions[0].resume_id == resume.id


def test_an_identical_deactivated_bullet_is_flagged_for_reactivation(session, career):
    profile_id = career.first_profile.id
    set_bullet_active(profile_id, session, career.first_bullet.id, active=False)
    draft = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[DraftBullet(text=career.first_bullet.text_es, chips=["python"])],
            )
        ],
    )
    resume = make_resume(session, profile_id, draft)

    plan = diff_draft(profile_id, session, draft)
    candidate = plan.roles[0].bullets[0]

    assert candidate.label == "changed"
    assert candidate.reactivates is True
    assert candidate.old_text is None, "nothing is rewritten, so there is no revision"

    apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    assert get_bullet(profile_id, session, career.first_bullet.id).active is True
    assert session.query(BulletRevision).count() == 0


def test_unchecked_candidates_change_nothing(session, career):
    profile_id = career.first_profile.id
    draft = full_draft()
    resume = make_resume(session, profile_id, draft)
    plan = diff_draft(profile_id, session, draft)

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=Selections(),
    )

    assert replace(result, track_id=None) == MergeResult(
        track_headline_filled=True,
        track_summary_filled=True,
        track_created=True,
    ), "the candidates write nothing; the document still lands in its own track"
    employers = [role.employer for role in list_roles(profile_id, session, active_only=False)]
    assert employers == ["Acme"]
    assert resume.merged_at is not None


def test_bullets_of_an_unchecked_new_role_are_counted_as_skipped(session, career):
    profile_id = career.first_profile.id
    draft = full_draft()
    resume = make_resume(session, profile_id, draft)
    plan = diff_draft(profile_id, session, draft)

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=Selections(bullets=frozenset({(0, 0)})),
    )

    assert result.skipped == 1
    assert result.bullets_created == 0
    assert len(list_bullets(profile_id, session, active_only=False)) == 1


def test_a_changed_education_reports_which_fields_moved(session, career):
    from src.education import create_education

    profile_id = career.first_profile.id
    create_education(
        profile_id,
        session,
        institution="Universidad Nacional de Ingeniería",
        degree="Bachiller en Ingeniería de Sistemas",
        field="Ingeniería Industrial",
        end_date=None,
    )
    draft = ResumeDraft(
        language="es",
        educations=[
            DraftEducation(
                institution="Universidad Nacional de Ingeniería",
                award="Bachiller en Ingeniería de Sistemas",
                field="Ingeniería de Sistemas",
                end_date="2019",
            )
        ],
    )

    plan = diff_draft(profile_id, session, draft)

    assert plan.educations[0].label == "changed"
    assert plan.educations[0].changes == ("field", "dates")


def test_a_foreign_resume_cannot_be_merged(session, career):
    draft = full_draft()
    resume = make_resume(session, career.first_profile.id, draft)

    result = apply_merge(
        career.second_profile.id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=diff_draft(career.second_profile.id, session, draft),
        selections=Selections(),
    )

    assert result is None
    assert resume.merged_at is None


def test_an_upload_tagged_with_a_track_appends_its_bullets_and_keeps_the_selection(
    session, career
):
    """F4 path 1: a résumé tagged with an existing track joins that track (N5 queue 1.2).

    A track with three hand-picked bullets, an upload tagged with it contributing two
    new bullets and one already selected → five in the track, the originals' order
    intact, and no duplicate row in `track_bullets`.
    """
    profile_id = career.first_profile.id
    track_id = career.first_track.id
    hand_picked = [
        create_bullet(
            profile_id,
            session,
            role_id=career.first_role.id,
            text_es=text,
            text_en=None,
        )
        for text in (
            "Primera línea elegida a mano",
            "Segunda línea elegida a mano",
            "Tercera línea elegida a mano",
        )
    ]
    session.commit()
    set_track_bullets(profile_id, session, track_id, [bullet.id for bullet in hand_picked])
    session.commit()

    draft = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[
                    DraftBullet(text="Nueva línea uno con Python", chips=["python"]),
                    DraftBullet(text="Nueva línea dos con Python", chips=["python"]),
                    DraftBullet(text=hand_picked[0].text_es, chips=[]),
                ],
            )
        ],
    )
    resume = make_resume(session, profile_id, draft, track_id=track_id)
    plan = diff_draft(profile_id, session, draft)

    assert [bullet.label for bullet in plan.roles[0].bullets] == ["new", "new", "unchanged"]

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    selected = track_bullets(profile_id, session, track_id)
    assert [bullet.id for bullet in selected[:3]] == [bullet.id for bullet in hand_picked], (
        "the hand-picked bullets keep their place and their order"
    )
    assert len(selected) == 5
    assert replace(result, track_id=None) == MergeResult(
        bullets_created=2, track_bullets_added=2
    )
    rows = session.scalars(select(TrackBullet).where(TrackBullet.track_id == track_id)).all()
    assert len(rows) == 5, "no duplicate row in track_bullets"
    positions = {row.bullet_id: row.position for row in rows}
    assert [positions[bullet.id] for bullet in hand_picked] == [0, 1, 2]
    assert sorted(positions.values()) == [0, 1, 2, 3, 4], "the new ones continue from the end"


def test_an_untagged_upload_creates_a_track_named_after_the_file(session, career):
    """F2.7: there is no no-track outcome — the file's stem names the new track."""
    profile_id = career.first_profile.id
    draft = full_draft()
    resume = make_resume(session, profile_id, draft, "cv 2026")
    plan = diff_draft(profile_id, session, draft)

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    assert result.track_created is True
    track = get_track(profile_id, session, result.track_id)
    assert track.name == "cv 2026"
    assert track.lang == "es"
    assert resume.track_id == track.id
    assert [bullet.text_es for bullet in track_bullets(profile_id, session, track.id)] == [
        "Modelé el riesgo de crédito con Python"
    ]


def test_a_second_upload_tagged_with_the_track_appends_skills_and_keeps_the_summary(
    session, career
):
    """F2.7's auto-fill: skills append de-duplicated, the summary is never replaced."""
    profile_id = career.first_profile.id
    first_draft = full_draft()
    first = make_resume(session, profile_id, first_draft, "cv uno")
    plan = diff_draft(profile_id, session, first_draft)
    result = apply_merge(
        profile_id,
        session,
        resume_id=first.id,
        draft=first_draft,
        plan=plan,
        selections=select_all(plan),
    )
    track_id = result.track_id
    track = get_track(profile_id, session, track_id)
    summary_id = track.summary_es_id
    assert summary_id is not None
    assert track.skills == ["python"]

    second_draft = ResumeDraft(
        language="es",
        headline="Otro titular",
        summary="Otro resumen que no debe entrar.",
        skills=["python", "machine learning"],
        roles=[
            DraftRole(
                employer="Globex",
                title="Data Scientist",
                start_date="2021-01",
                bullets=[
                    DraftBullet(text="Modelé el riesgo de crédito con Python", chips=["python"])
                ],
            )
        ],
    )
    second = make_resume(session, profile_id, second_draft, "cv dos", track_id=track_id)
    plan = diff_draft(profile_id, session, second_draft)
    second_result = apply_merge(
        profile_id,
        session,
        resume_id=second.id,
        draft=second_draft,
        plan=plan,
        selections=select_all(plan),
    )

    track = get_track(profile_id, session, track_id)
    assert sorted(track.skills) == ["machine learning", "python"], "appended, de-duplicated"
    assert second_result.track_skills_added == 1
    assert track.summary_es_id == summary_id, "a summary the track has is never replaced"
    assert second_result.track_summary_kept is True
    assert track.headline_es == "Analista de datos", "nor is a headline it already has"
    assert second_result.track_headline_kept is True


def test_an_english_upload_fills_the_en_slots_and_leaves_the_es_ones(session, career):
    """F4.1: the slots are per language; a document fills its own and touches no other."""
    profile_id = career.first_profile.id
    es_draft = full_draft()
    first = make_resume(session, profile_id, es_draft, "cv es")
    plan = diff_draft(profile_id, session, es_draft)
    result = apply_merge(
        profile_id,
        session,
        resume_id=first.id,
        draft=es_draft,
        plan=plan,
        selections=select_all(plan),
    )
    track_id = result.track_id
    track = get_track(profile_id, session, track_id)
    es_summary_id = track.summary_es_id
    assert track.headline_es == "Analista de datos"
    assert track.headline_en is None and track.summary_en_id is None

    en_draft = ResumeDraft(
        language="en",
        headline="Data analyst",
        summary="Five years automating reporting.",
        skills=["python"],
        roles=[
            DraftRole(
                employer="Globex",
                title="Data Scientist",
                start_date="2021-01",
                bullets=[DraftBullet(text="Modeled credit risk with Python", chips=["python"])],
            )
        ],
    )
    second = make_resume(session, profile_id, en_draft, "cv en", track_id=track_id)
    plan = diff_draft(profile_id, session, en_draft)
    second_result = apply_merge(
        profile_id,
        session,
        resume_id=second.id,
        draft=en_draft,
        plan=plan,
        selections=select_all(plan),
    )

    track = get_track(profile_id, session, track_id)
    assert track.headline_en == "Data analyst"
    assert track.headline_es == "Analista de datos", "the Spanish headline is untouched"
    assert track.summary_en_id is not None and track.summary_en_id != es_summary_id
    assert track.summary_es_id == es_summary_id, "the Spanish summary is untouched"
    assert second_result.track_headline_filled and second_result.track_summary_filled


def test_a_summary_already_in_the_pool_is_matched_not_duplicated(session, career):
    """F2.7: the pool matches after folding — case, accents and whitespace are not new."""
    profile_id = career.first_profile.id
    draft = full_draft()
    before = len(list_summaries(profile_id, session))
    first = make_resume(session, profile_id, draft, "cv uno")
    plan = diff_draft(profile_id, session, draft)
    first_result = apply_merge(
        profile_id,
        session,
        resume_id=first.id,
        draft=draft,
        plan=plan,
        selections=select_all(plan),
    )

    variant = draft.model_copy(update={"summary": "CINCO AÑOS   automatizando reportes."})
    second = make_resume(session, profile_id, variant, "cv dos")
    plan = diff_draft(profile_id, session, variant)
    second_result = apply_merge(
        profile_id,
        session,
        resume_id=second.id,
        draft=variant,
        plan=plan,
        selections=select_all(plan),
    )

    assert len(list_summaries(profile_id, session)) == before + 1
    one = get_track(profile_id, session, first_result.track_id)
    two = get_track(profile_id, session, second_result.track_id)
    assert one.summary_es_id == two.summary_es_id, "both tracks cite the same pool row"
    pooled = session.get(Summary, one.summary_es_id)
    assert pooled.source_resume_id == first.id, "the row keeps the résumé it came from"
    assert second_result.track_summary_filled is True, "the new track's slot is filled"