"""N8.1: letter settings, the template↔track link, and the stored letter.

The schema is additive, so the tests here are about the two rules it carries: the
blocks are one row per profile and language, and a saved letter is a snapshot that a
template deletion cannot reach.
"""

from decimal import Decimal

from src.applications import create_application, save_application_letter
from src.deletion import delete_everything, delete_letter_template, impact_everything
from src.letters import (
    create_letter,
    get_letter,
    get_letter_settings,
    list_letters,
    save_letter_settings,
    update_letter,
)
from tests.conftest import login


def test_settings_upsert_by_profile_and_language(session, career):
    first = save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana\npersona@example.com",
        greeting="Estimado equipo,",
        closing="Quedo a disposición.",
        sign_off="Ana",
        voice_notes="Tuteo.",
    )
    same = save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana\npersona@example.com",
        greeting="Hola,",
        closing="Quedo a disposición.",
        sign_off="Ana",
        voice_notes="Tuteo.",
    )
    english = save_letter_settings(
        career.first_profile.id,
        session,
        lang="en",
        header="Ana",
        greeting="Dear team,",
        closing="Best regards,",
        sign_off="Ana",
    )
    session.commit()

    assert first.id == same.id, "one row per language"
    assert english.id != first.id
    assert get_letter_settings(career.first_profile.id, session, "es").greeting == "Hola,"
    assert get_letter_settings(career.first_profile.id, session, "en").greeting == "Dear team,"
    assert get_letter_settings(career.first_profile.id, session, "en").voice_notes == ""


def test_settings_are_owner_scoped(session, career):
    save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana",
        greeting="Hola,",
        closing="Quedo.",
        sign_off="Ana",
    )
    session.commit()

    assert get_letter_settings(career.second_profile.id, session, "es") is None


def test_a_template_links_only_a_track_of_its_own_profile(session, career):
    mine = create_letter(
        career.first_profile.id,
        session,
        name="Corporativo",
        applies_when="Banca",
        presentation="Me presento.",
        achievements="Logros.",
        track_id=career.first_track.id,
    )
    theirs = create_letter(
        career.first_profile.id,
        session,
        name="Ajeno",
        applies_when="",
        presentation="x",
        achievements="y",
        track_id=career.second_track.id,
    )
    session.commit()

    assert mine.track_id == career.first_track.id
    assert theirs.track_id is None, "another profile's track links nothing"

    updated = update_letter(
        career.first_profile.id,
        session,
        mine.id,
        name="Corporativo",
        applies_when="Banca",
        presentation="Me presento.",
        achievements="Logros.",
        track_id=career.second_track.id,
    )
    assert updated is not None and updated.track_id is None
    assert get_letter(career.first_profile.id, session, mine.id) is not None


def test_deleting_a_template_keeps_the_saved_letter(session, career):
    letter = create_letter(
        career.first_profile.id,
        session,
        name="Corporativo",
        applies_when="Banca",
        presentation="Me presento.",
        achievements="Logros.",
    )
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:letter-snapshot",
        report={"score": {}, "llm": {"calls": []}},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal(0),
    )
    save_application_letter(
        career.first_profile.id,
        session,
        application.id,
        text="Estimado equipo: ...",
        template_id=letter.id,
    )
    session.commit()
    assert application.letter_template_id == letter.id

    assert delete_letter_template(career.first_profile.id, session, letter.id) is not None
    session.commit()
    session.expire_all()
    assert application.letter_text == "Estimado equipo: ...", "the snapshot survives"
    assert application.letter_template_id is None, "the link is gone"


def test_everything_counts_and_removes_letter_settings(session, career):
    save_letter_settings(
        career.first_profile.id,
        session,
        lang="es",
        header="Ana",
        greeting="Hola,",
        closing="Quedo.",
        sign_off="Ana",
    )
    session.commit()

    assert impact_everything(career.first_profile.id, session)["letter_settings"] == 1

    totals = delete_everything(career.first_profile.id, session)
    session.commit()

    assert totals["letter_settings"] == 1
    assert get_letter_settings(career.first_profile.id, session, "es") is None
    assert len(list_letters(career.first_profile.id, session)) == 0


def test_the_letters_page_still_renders(client, session, career):
    login(client, career.first.email)

    assert client.get("/letters").status_code == 200
