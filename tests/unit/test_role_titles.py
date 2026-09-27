"""Role titles in two languages (PRD F4.2, 2026-09-27).

One title per language, one primary language per role, and the four rules the
`0011` backfill used. The rules live in `roles.role_language`, which is what every
later write reads — the migration backfilled the rows that already existed with
the same order, and these are the cases it had to decide.
"""

import hashlib

from src.bullets import create_bullet
from src.resumes import create_resume
from src.roles import create_role, role_language, role_title, update_role
from src.tracks import create_track, set_track_bullets
from src.web.alerts import language_alert


def document(session, profile_id, name: str, language: str):
    return create_resume(
        profile_id,
        session,
        filename=f"{name}.docx",
        data=b"bytes",
        sha256=hashlib.sha256(name.encode()).hexdigest(),
        gate={},
        draft={"language": language},
    )


def test_the_provenance_rule_reads_the_resumes_draft_language(session, career):
    """Rule 1: the résumé behind the role's earliest bullet with provenance wins."""
    profile_id = career.first_profile.id
    english = document(session, profile_id, "cv-en", "en")
    role = create_role(
        profile_id, session, employer="ONG Andina", title_es="Coordinadora", title_en=None
    )
    bullet = create_bullet(
        profile_id,
        session,
        role_id=role.id,
        text_es=None,
        text_en="Coordinated the programme",
        chips=[],
    )
    bullet.source_resume_id = english.id
    session.flush()

    assert role_language(profile_id, session, role.id) == "en"


def test_the_majority_rule_reads_the_bullets_that_are_written(session, career):
    """Rule 2: the language most of its bullets are written in, a tie falling through."""
    profile_id = career.first_profile.id
    role = create_role(
        profile_id, session, employer="Acme", title_es="Analista", title_en=None
    )
    create_bullet(
        profile_id, session, role_id=role.id, text_es=None, text_en="One", chips=[]
    )
    create_bullet(
        profile_id, session, role_id=role.id, text_es=None, text_en="Two", chips=[]
    )

    assert role_language(profile_id, session, role.id) == "en"

    # A tie — one bullet carrying both languages — is not a language: it falls
    # through to the track that holds the bullet.
    tied = create_role(
        profile_id, session, employer="Globex", title_es="Ingeniera", title_en=None
    )
    both = create_bullet(
        profile_id, session, role_id=tied.id, text_es="Uno", text_en="One", chips=[]
    )
    track = create_track(profile_id, session, name="Data", lang="en")
    set_track_bullets(profile_id, session, track.id, [both.id])

    assert role_language(profile_id, session, tied.id) == "en"


def test_the_track_rule_then_the_default(session, career):
    """Rule 3 reads a track holding one of the bullets; with nothing to read, `es`."""
    profile_id = career.first_profile.id
    role = create_role(profile_id, session, employer="Acme", title_es="Analista", title_en=None)

    assert role_language(profile_id, session, role.id) == "es", "no bullets, no track"

    spanish_track = create_track(profile_id, session, name="Analista", lang="es")
    bullet = create_bullet(
        profile_id, session, role_id=role.id, text_es="Uno", text_en="One", chips=[]
    )
    set_track_bullets(profile_id, session, spanish_track.id, [bullet.id])

    assert role_language(profile_id, session, role.id) == "es"


def test_a_known_language_short_circuits_the_rules(session, career):
    """A merge creating a role from a document knows the draft's language."""
    profile_id = career.first_profile.id
    role = create_role(
        profile_id,
        session,
        employer="Globex",
        title_es="Analista",
        title_en="Analyst",
        language="en",
    )

    assert role_language(profile_id, session, role.id, language="en") == "en"
    assert role.title_en == "Analyst" and role.title_es == "Analista"


def test_the_primary_language_decides_what_title_holds(session, career):
    """`title` mirrors the primary language's slot — the other one only when the
    primary is empty (F4.2). It is never a translation: an empty column stays empty."""
    profile_id = career.first_profile.id
    english_bullet_role = create_role(
        profile_id, session, employer="Acme", title_es=None, title_en="Data Analyst"
    )
    create_bullet(
        profile_id, session, role_id=english_bullet_role.id, text_es=None, text_en="One", chips=[]
    )

    # The role's language is English (rule 2), so `title` is the English slot.
    updated = update_role(
        profile_id,
        session,
        english_bullet_role.id,
        employer="Acme",
        title_es="Analista de datos",
        title_en="Data Analyst",
        start_date=None,
        end_date=None,
    )

    assert updated is not None
    assert updated.title == "Data Analyst"
    assert updated.title_es == "Analista de datos"
    assert role_title(updated, "es") == ("Analista de datos", False)
    assert role_title(updated, "en") == ("Data Analyst", False)

    # A Spanish role with an English title typed in still mirrors the Spanish slot.
    spanish = create_role(
        profile_id, session, employer="Initech", title_es="Consultora", title_en="Consultant"
    )
    assert spanish.title == "Consultora"
    assert role_title(spanish, "en") == ("Consultant", False)


def test_a_title_exists_only_in_the_other_language_is_read_as_a_fallback(session, career):
    """Reading, not writing: the posting's language first, the other one marked."""
    profile_id = career.first_profile.id
    role = create_role(
        profile_id, session, employer="Acme", title_es="Analista de datos", title_en=None
    )

    assert role_title(role, "en") == ("Analista de datos", True)
    assert role_title(role, "es") == ("Analista de datos", False)
    assert role_title(role, None) == ("Analista de datos", False)


def alert(**overrides) -> dict:
    base = {
        "kind": "language_mismatch",
        "posting": "en",
        "other": "es",
        "fallback_bullets": 3,
        "bullets": 8,
        "fallback_titles": 0,
        "titles": 2,
        "fallback_headline": False,
        "fallback_summary": False,
    }
    return {**base, **overrides}


def test_the_language_alert_joins_one_item():
    text = language_alert(alert(), "es")

    assert "3 de tus 8 bullets solo existen en español" in text
    assert "envía la versión en inglés" in text


def test_the_language_alert_joins_two_items():
    assert "3 de tus 8 bullets y tu titular solo existen" in language_alert(
        alert(fallback_headline=True), "es"
    )
    assert "3 de tus 8 bullets y tus cargos solo existen" in language_alert(
        alert(fallback_titles=2), "es"
    )


def test_the_language_alert_joins_three_items():
    """The bug the join exists for: "and … and" is not a sentence."""
    text = language_alert(alert(fallback_headline=True, fallback_summary=True), "es")

    assert "3 de tus 8 bullets, tu titular y tu resumen solo existen en español" in text

    with_titles = language_alert(alert(fallback_titles=2, fallback_headline=True), "es")
    assert "3 de tus 8 bullets, tus cargos y tu titular solo existen" in with_titles

    english = language_alert(
        alert(fallback_headline=True, fallback_summary=True), "en"
    )
    assert "3 of your 8 bullets, your headline and your summary exist only in Spanish" in english


def test_an_alert_stored_before_titles_had_a_language_still_reads():
    """A report written before 2026-09-27 has no `fallback_titles`: same sentence."""
    old = {
        "kind": "language_mismatch",
        "posting": "en",
        "other": "es",
        "fallback_bullets": 1,
        "bullets": 1,
        "fallback_headline": True,
        "fallback_summary": False,
    }

    assert "1 de tus 1 bullets y tu titular solo existen en español" in language_alert(old, "es")
