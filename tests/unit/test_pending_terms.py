"""Pending terms (PRD F2.9, adopted 2026-09-27): a chip the vocabulary refuses is
kept, logged, counted for nothing, and resolved by promotion.

The decision that shrank F3.1 left this as the whole of what survives of the open
vocabulary: the vocabulary does not grow by itself, but nothing a user typed is
lost on the way to the operator's decision.
"""

from sqlalchemy import select

from src.bullets import create_bullet, list_bullets, update_bullet
from src.documents import track_document
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft
from src.ingest.merge import Selections, apply_merge, diff_draft
from src.models import UnmappedTerm
from src.tracks import set_track_bullets
from src.vocabulary import list_unmapped, promote_alias, resolve_pending
from tests.conftest import login
from tests.unit.test_ingest_merge import make_resume


def unmapped(session, term: str) -> UnmappedTerm:
    record = session.scalar(select(UnmappedTerm).where(UnmappedTerm.term == term))
    assert record is not None, "an unknown chip is logged, never swallowed"
    return record


def test_an_unknown_chip_survives_creation_folded_and_logged(session, career):
    """Folded, de-duplicated, in the order typed — and in the log the operator reads."""
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Coordiné la migración del aula virtual",
        text_en=None,
        chips=["Moodle", "moodle", "Canvas", "python"],
    )

    assert bullet.skills == ["python"]
    assert bullet.pending_terms == ["moodle", "canvas"]
    assert unmapped(session, "moodle").seen_count == 1
    assert "canvas" in [record.term for record in list_unmapped(session, status="new")]


def test_editing_a_bullet_replaces_pending_terms_like_skills(session, career):
    """The form's chips are the truth on update; the pending set follows them."""
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Coordiné la migración del aula virtual",
        text_en=None,
        chips=["moodle"],
    )

    updated = update_bullet(
        career.first_profile.id,
        session,
        bullet.id,
        text_es="Coordiné la migración del aula virtual",
        text_en=None,
        chips=["moodle", "salesforce"],
    )
    assert updated is not None and updated.pending_terms == ["moodle", "salesforce"]

    # Editing it away is a decision too: the vocabulary has not changed, the form did.
    cleared = update_bullet(
        career.first_profile.id,
        session,
        bullet.id,
        text_es="Coordiné la migración del aula virtual",
        text_en=None,
        chips=[],
    )
    assert cleared is not None and cleared.pending_terms == []


def test_a_pending_term_counts_nowhere(session, career):
    """Not in the chips, not in any pool, not in the track, not in the document the
    scorer reads — the vocabulary does not change by itself."""
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Coordiné la migración del aula virtual",
        text_en=None,
        chips=["moodle"],
    )
    set_track_bullets(
        career.first_profile.id,
        session,
        career.first_track.id,
        [*(entry.id for entry in list_bullets(career.first_profile.id, session)), bullet.id],
    )

    document = track_document(career.first_profile.id, session, career.first_track, "es")

    assert "moodle" not in bullet.skills
    assert "moodle" not in career.first_profile.skills
    assert "moodle" not in career.first_track.skills
    assert not any("moodle" in unit.text for unit in document)


def test_the_merge_keeps_the_unknown_chip_on_the_bullet_it_created(session, career):
    """The merge already writes through `create_bullet`, so this is the same rule
    reaching the import path rather than a second one."""
    profile_id = career.first_profile.id
    draft = ResumeDraft(
        language="es",
        headline="Coordinadora de programas",
        summary=None,
        skills=[],
        roles=[
            DraftRole(
                employer="ONG Andina",
                title="Coordinadora",
                start_date="2020-01",
                bullets=[DraftBullet(text="Implementé Moodle para 300 alumnos", chips=["Moodle"])],
            )
        ],
    )
    resume = make_resume(session, profile_id, draft)
    plan = diff_draft(profile_id, session, draft)

    result = apply_merge(
        profile_id,
        session,
        resume_id=resume.id,
        draft=draft,
        plan=plan,
        selections=Selections(
            roles=frozenset(range(len(plan.roles))),
            bullets=frozenset({(0, 0)}),
        ),
    )

    assert result is not None and result.bullets_created == 1
    created = [
        bullet
        for bullet in list_bullets(profile_id, session)
        if bullet.source_resume_id == resume.id
    ]
    assert [bullet.pending_terms for bullet in created] == [["moodle"]]
    assert created[0].skills == []
    assert unmapped(session, "moodle").seen_count == 1


def test_promotion_resolves_the_term_on_every_profile(session, career):
    """Two profiles, one vocabulary (F2.9): promoting is one decision about every
    bullet holding the term, and a track's selection is untouched by it."""
    first = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Migré el aula virtual",
        text_en=None,
        chips=["moodle"],
    )
    second = create_bullet(
        career.second_profile.id,
        session,
        role_id=career.second_role.id,
        text_es="Di clase en el aula virtual",
        text_en=None,
        chips=["moodle"],
    )
    tracks_before = list(career.first_track.skills)

    promote_alias(session, "moodle", "moodle")

    assert first.pending_terms == [] and second.pending_terms == []
    assert "moodle" in first.skills and "moodle" in second.skills
    assert "moodle" in career.first_profile.skills
    assert "moodle" in career.second_profile.skills
    assert career.first_track.skills == tracks_before


def test_promotion_resolves_the_typed_word_to_its_canonical(session, career):
    """An alias promoted onto an existing canonical resolves to that canonical."""
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Puse el modelo en producción",
        text_en=None,
        chips=["mlops"],
    )
    assert bullet.pending_terms == ["mlops"]

    promote_alias(session, "machine learning", "mlops")

    assert bullet.pending_terms == []
    assert bullet.skills == ["machine learning"]
    assert "machine learning" in career.first_profile.skills


def test_promotion_of_a_term_the_vocabulary_still_does_not_know_resolves_nothing(
    session, career
):
    create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Migré el aula virtual",
        text_en=None,
        chips=["moodle"],
    )

    assert resolve_pending(session, "blackboard") == 0


def test_the_edit_screen_labels_the_pending_chip(client, career):
    """The screen the user edits on shows what is stored as pending, and the chip
    field carries it back so saving cannot lose it."""
    login(client, "persona@example.com")

    response = client.get(f"/bullets/{career.first_bullet.id}/edit")

    assert response.status_code == 200
    assert "pendiente de vocabulario" in response.text
    assert f'value="{career.first_bullet.skills[0]}, {career.first_bullet.pending_terms[0]}"' in (
        response.text
    )


def test_the_role_screen_labels_the_pending_chip(client, career):
    login(client, "persona@example.com")

    response = client.get(f"/roles/{career.first_role.id}")

    assert response.status_code == 200
    assert "pendiente de vocabulario" in response.text
    assert career.first_bullet.pending_terms == ["cobalto"]
