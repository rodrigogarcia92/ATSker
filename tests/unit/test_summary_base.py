"""F7.3 rule 3: the base summary is chosen once and is a source for the validators (queue M2)."""

import uuid
from datetime import UTC, datetime, timedelta

from src.generate.proposals import (
    BASE_CV,
    BASE_OTHER_LANGUAGE,
    BASE_TRACK,
    accept_summary,
    base_summary,
    check_summary,
    summary_sources,
)
from src.generate.validators import Sources, validate
from src.summaries import create_summary, set_summary_active
from src.tracks import get_track, set_track_summary
from tests.unit.test_generation import stored_application


def _track(session, career):
    return get_track(career.first_profile.id, session, career.first_track.id)


def test_the_base_is_the_tracks_own_summary_first(session, career):
    pid = career.first_profile.id
    own = create_summary(pid, session, text="Resumen de la línea.", lang="es")
    create_summary(pid, session, text="Resumen del CV.", lang="es", source_resume_id=uuid.uuid4())
    set_track_summary(pid, session, career.first_track.id, lang="es", summary_id=own.id)

    base = base_summary(pid, session, _track(session, career), "es")

    assert (base.text, base.summary_id, base.origin) == (
        "Resumen de la línea.",
        str(own.id),
        BASE_TRACK,
    )


def test_the_base_falls_back_to_the_latest_active_uploaded_summary(session, career):
    pid = career.first_profile.id
    track = _track(session, career)
    create_summary(pid, session, text="Escrito a mano.", lang="es")
    old = create_summary(pid, session, text="CV viejo.", lang="es", source_resume_id=uuid.uuid4())
    newest = create_summary(
        pid, session, text="CV nuevo.", lang="es", source_resume_id=uuid.uuid4()
    )
    inactive = create_summary(
        pid, session, text="CV más nuevo pero retirado.", lang="es", source_resume_id=uuid.uuid4()
    )
    set_summary_active(pid, session, inactive.id, active=False)
    # Stamp the order explicitly: the clock on some platforms is too coarse to separate rows.
    for offset, entry in enumerate((old, newest, inactive)):
        entry.created_at = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=offset)
    create_summary(pid, session, text="CV in English.", lang="en", source_resume_id=uuid.uuid4())

    base = base_summary(pid, session, track, "es")

    assert (base.text, base.origin) == ("CV nuevo.", BASE_CV)
    assert base.summary_id == str(newest.id) != str(old.id)


def test_the_base_may_be_the_tracks_summary_in_the_other_language(session, career):
    pid = career.first_profile.id
    english = create_summary(pid, session, text="Data analyst.", lang="en")
    set_track_summary(pid, session, career.first_track.id, lang="en", summary_id=english.id)

    base = base_summary(pid, session, _track(session, career), "es")

    assert (base.text, base.origin) == ("Data analyst.", BASE_OTHER_LANGUAGE)


def test_with_nothing_there_there_is_no_base(session, career):
    pid = career.first_profile.id
    create_summary(pid, session, text="Escrito a mano.", lang="es")  # not from a CV

    assert base_summary(pid, session, _track(session, career), "es") is None


def test_another_profiles_summary_is_never_the_base(session, career):
    other = career.second_profile.id
    create_summary(other, session, text="Ajeno.", lang="es", source_resume_id=uuid.uuid4())
    foreign = create_summary(other, session, text="Ajeno en la línea.", lang="es")
    track = _track(session, career)
    track.summary_es_id = foreign.id  # a slot pointing at a foreign row is not honoured

    assert base_summary(career.first_profile.id, session, track, "es") is None


def test_a_number_only_in_the_base_passes_literal_preservation():
    base = "Analista con más de 8 años de experiencia."
    text = {"summary": {"text": "Analista con más de 8 años.", "cites": ["summary:s1", "b1"]}}
    with_base = Sources(bullets={"b1": "Automaticé el reporte."}, summaries={"s1": base})
    without = Sources(bullets={"b1": "Automaticé el reporte."})

    def check(sources):
        return validate(text, sources=sources, profile_id=None, session=None, kind="summary")

    assert check(with_base) == []
    assert [v.rule for v in check(without)] == ["provenance", "literal"]


def test_citing_a_foreign_summary_is_a_provenance_violation():
    sources = Sources(bullets={"b1": "Automaticé."}, summaries={"mine": "Mi resumen."})
    out = {"summary": {"text": "Automaticé.", "cites": [f"summary:{uuid.uuid4()}", "b1"]}}

    violations = validate(out, sources=sources, profile_id=None, session=None, kind="summary")

    assert [v.rule for v in violations] == ["provenance"]


def test_the_sources_hold_the_same_base_the_generator_uses(session, career):
    pid = career.first_profile.id
    application = stored_application(session, career)
    base = create_summary(
        pid, session, text="Hola de 8 años.", lang="es", source_resume_id=uuid.uuid4()
    )

    sources = summary_sources(pid, session, _track(session, career), "es", application)

    assert sources.summaries == {str(base.id): "Hola de 8 años."}
    assert "Analista de datos" in sources.titles
    assert f"summary:{base.id}" in sources.ids


def test_with_no_base_the_sources_are_as_before(session, career):
    application = stored_application(session, career)

    sources = summary_sources(
        career.first_profile.id, session, _track(session, career), "es", application
    )

    assert sources.summaries == {}


def test_the_posting_title_is_a_permitted_proper_noun(session, career):
    pid = career.first_profile.id
    application = stored_application(session, career)
    application.title = "Analista Senior Zafiro"
    out = {
        "summary": {
            "text": "Soy Analista Senior Zafiro.",
            "cites": [str(career.first_bullet.id)],
        }
    }

    assert check_summary(pid, session, application, _track(session, career), out) == []


def test_accepting_a_summary_that_cites_the_base_writes_the_pool_row_only(session, career):
    pid = career.first_profile.id
    application = stored_application(session, career)
    base = create_summary(
        pid, session, text="Con más de 8 años.", lang="es", source_resume_id=uuid.uuid4()
    )
    track = _track(session, career)
    skills_before = list(track.skills or [])

    summary, violations = accept_summary(
        pid,
        session,
        application,
        track,
        text="Con más de 8 años.",
        cites=[f"summary:{base.id}"],
        use_in_track=False,
    )

    assert violations == [] and summary is not None and summary.id != base.id
    assert list(track.skills or []) == skills_before


def test_accepting_a_foreign_summary_cite_is_refused(session, career):
    pid = career.first_profile.id
    application = stored_application(session, career)
    foreign = create_summary(career.second_profile.id, session, text="Ajeno.", lang="es")

    summary, violations = accept_summary(
        pid,
        session,
        application,
        _track(session, career),
        text="Ajeno.",
        cites=[f"summary:{foreign.id}"],
        use_in_track=False,
    )

    assert summary is None and [v.rule for v in violations] == ["provenance"]
