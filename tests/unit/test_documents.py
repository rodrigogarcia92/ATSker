"""The document behind F5.5.1's one source of truth (PRD F4.1).

Three things are pinned here: every unit records whether its text is a language
fallback, a Spanish-only track analysed against an English posting returns its
Spanish text marked as such, and the no-track document is byte-identical to what
`searchable_units` produced before tracks spoke two languages — the regression
that would silently change what a recruiter's query runs against.
"""

from src.bullets import create_bullet
from src.certifications import create_certification
from src.documents import track_document
from src.education import create_education
from src.search.boolean import SearchUnit
from src.search.sources import searchable_units
from src.summaries import create_summary
from src.tracks import create_track, set_track_bullets, update_track


def test_every_unit_records_whether_its_text_is_a_language_fallback(session, career):
    """F4.1: a fallback is per item, and it is recorded — a Spanish summary graded
    against an English posting is weaker evidence and the report says so."""
    profile_id = career.first_profile.id
    es_summary = create_summary(profile_id, session, text="Resumen en español.", lang="es")
    en_summary = create_summary(profile_id, session, text="An English summary.", lang="en")
    update_track(
        profile_id,
        session,
        career.first_track.id,
        name=career.first_track.name,
        applies_when=career.first_track.applies_when,
        lang="en",
        headline_es="Analista de datos",
        headline_en="Data analyst",
        summary_es_id=es_summary.id,
        summary_en_id=en_summary.id,
    )
    session.flush()

    english = {(unit.kind, unit.text): unit.fallback for unit in track_document(
        profile_id, session, career.first_track, "en"
    )}
    spanish = {(unit.kind, unit.text): unit.fallback for unit in track_document(
        profile_id, session, career.first_track, "es"
    )}

    assert english[("headline", "Data analyst")] is False
    assert english[("summary", "An English summary.")] is False
    assert english[("bullet", career.first_bullet.text_es)] is True, (
        "the bullet is Spanish-only, so its English reading is a fallback"
    )
    assert spanish[("headline", "Analista de datos")] is False
    assert spanish[("summary", "Resumen en español.")] is False
    assert spanish[("bullet", career.first_bullet.text_es)] is False


def test_a_spanish_only_track_against_an_english_posting_keeps_spanish_marked_as_fallback(
    session, career
):
    """The fallback is the weaker evidence, never a translation that does not exist."""
    profile_id = career.first_profile.id
    career.first_profile.skills = ["python", "machine learning"]
    summary = create_summary(profile_id, session, text="Cinco años automatizando.", lang="es")
    track = create_track(
        profile_id,
        session,
        name="Solo español",
        lang="es",
        headline_es="Analista de datos",
        summary_es_id=summary.id,
        skills=["python", "cobalto"],
    )
    set_track_bullets(profile_id, session, track.id, [career.first_bullet.id])
    session.flush()

    document = track_document(profile_id, session, track, "en")

    texts = [(unit.kind, unit.text) for unit in document]
    assert ("headline", "Analista de datos") in texts
    assert ("summary", "Cinco años automatizando.") in texts
    assert ("skills_list", "python") in texts, "the pool selection is the skills section"
    assert ("bullet", career.first_bullet.text_es) in texts
    marked = {unit.kind: unit.fallback for unit in document}
    assert marked["headline"] is True
    assert marked["summary"] is True
    assert marked["bullet"] is True
    assert marked["skills_list"] is False, "canonical names carry no language"
    assert all("cobalto" not in unit.text for unit in document), (
        "a skill outside the pool cannot be on a track (F4.1)"
    )


def test_no_track_searchable_units_are_byte_identical_to_the_previous_output(
    session, career, vocabulary
):
    """The pre-F4.1 `searchable_units`, unit for unit, in its own order.

    Pinned rather than recomputed: this is the text a recruiter's boolean query and
    the keyword scorer run against, and a silent change here would move every stored
    scan's meaning. The chips the bullets carry are what F5.2 always searched —
    `profiles.skills` is still not read (decision 32).
    """
    profile_id = career.first_profile.id
    career.first_profile.headline = "Analista de datos"
    career.first_profile.summary = "Cinco anos automatizando reportes para direccion."
    second = create_bullet(
        profile_id,
        session,
        role_id=career.first_role.id,
        text_es="Modelé el riesgo con machine learning",
        text_en=None,
        chips=["ml"],
    )
    create_education(
        profile_id,
        session,
        institution="Universidad Nacional de Ingenieria",
        degree="Ingenieria",
        field="Sistemas",
    )
    create_certification(profile_id, session, name="Certificado Azure", issuer="Microsoft")
    session.flush()

    units = searchable_units(track_document(profile_id, session, None, "es"))

    assert units == [
        SearchUnit(
            "bullet", "Reduje 30% el tiempo de reporte con Python", str(career.first_bullet.id)
        ),
        SearchUnit("bullet", "Modelé el riesgo con machine learning", str(second.id)),
        SearchUnit("skill", "machine learning"),
        SearchUnit("skill", "python"),
        SearchUnit("headline", "Analista de datos"),
        SearchUnit("summary", "Cinco anos automatizando reportes para direccion."),
        SearchUnit("role", "Analista de datos"),
        SearchUnit("education", "Universidad Nacional de Ingenieria Ingenieria Sistemas"),
        SearchUnit("certification", "Certificado Azure Microsoft"),
    ]
