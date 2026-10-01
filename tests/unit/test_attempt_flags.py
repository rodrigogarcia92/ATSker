"""The new-in-this-document flags and the change list (PRD F10.5, F10.4 step 4, B.4).

The file was edited outside ATSker, so the F7.3 extractors are pointed at it: a skill
the pool does not hold and a number no stored row supports are flagged, the flag
survives "Descartar", and the change list names what moved against the previous
attempt.
"""

import pytest

from src.attempt_flags import discard_attempt, document_flags
from src.bullets import create_bullet
from src.certifications import create_certification
from src.education import create_education
from src.extract import client as extract_client
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft
from src.models import ApplicationAttempt
from src.summaries import create_summary
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    grading_payload,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def upload(client, application_id, data, name: str = "cv.docx"):
    return client.post(
        f"/applications/{application_id}/attempts",
        files={"file": (name, data, DOCX_TYPE)},
        follow_redirects=False,
    )


def _attempts(session):
    return (
        session.query(ApplicationAttempt)
        .order_by(ApplicationAttempt.attempt_no)
        .all()
    )


def test_a_skill_the_pool_does_not_hold_is_flagged_and_survives_discard(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, skills=("machine learning",)
    )

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))

    attempt = _attempts(session)[0]
    assert "machine learning" in attempt.report["flags"]["skills"]
    # The unheld skill lifts Keywords past the analysis's ceiling (E2): the F10.5 signal that
    # the file claims more than the material holds.
    assert attempt.job_match > attempt.ceiling_high
    assert attempt.report["flags"]["above_ceiling"] is True

    discard_attempt(attempt)
    session.commit()

    fresh = _attempts(session)[0]
    assert fresh.report["draft"] is None
    assert "machine learning" in fresh.report["flags"]["skills"], "the flag stays"


def test_an_invented_number_is_flagged(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    invented = f"{career.first_bullet.text_es} y mejoré el cierre un 37%"
    provider.answers["ResumeExtraction"] = resume_payload(invented)
    provider.answers["EvidenceGrading"] = grading_payload(None)

    upload(client, application.id, docx_bytes("Experiencia", invented))

    attempt = _attempts(session)[0]
    assert "37%" in attempt.report["flags"]["claims"]


def test_the_change_list_names_the_search_the_document_now_passes(
    client, session, career, provider
):
    """A bullet the file adds brings `machine learning`, so the strict search passes."""
    extra = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Entrené un modelo de machine learning en producción",
        text_en=None,
        chips=[],
    )
    session.commit()
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    provider.answers["ResumeExtraction"] = resume_payload(
        career.first_bullet.text_es, extra.text_es
    )
    upload(
        client,
        application.id,
        docx_bytes("Experiencia", career.first_bullet.text_es, extra.text_es),
    )

    first, second = _attempts(session)
    assert first.report["change"] == {}, "there was nothing before the first attempt"
    assert second.report["change"]["searches_found"] == ["strict"]


# --- D4: the flags read everything the user has stored (F10.5) ---


def _claims(session, career, *texts: str) -> list[str]:
    """The file's unsupported claims."""
    draft = ResumeDraft(
        roles=[
            DraftRole(
                employer="Acme",
                title="Analista de datos",
                bullets=[DraftBullet(text=text) for text in texts],
            )
        ],
    )
    return document_flags(career.first_profile.id, session, draft=draft)["claims"]


def test_ten_plus_is_ten(session, career):
    create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es="Trabajé 10 years con datos de salud",
        text_en=None,
        chips=[],
    )

    assert _claims(session, career, "Más de 10+ years con datos de salud") == []
    assert _claims(session, career, "Más de 12+ years con datos") == ["12+"]


def test_a_word_of_a_pool_canonical_is_supported(session, career):
    career.first_profile.skills = ["data science", "generative ai"]
    session.flush()

    claims = _claims(session, career, "apliqué Data Science y Generative AI en reportes")

    assert claims == [], "Data, Science, Generative and AI are words of held canonicals"


def test_a_stored_education_supports_its_words(session, career):
    create_education(
        career.first_profile.id, session, institution="Universidad Nacional Ejemplo"
    )

    assert _claims(session, career, "dicté un taller en la Universidad Nacional Ejemplo") == []


def test_certifications_track_text_and_the_display_name_support_their_words(session, career):
    create_certification(
        career.first_profile.id, session, name="Google Analytics", issuer="Coursera"
    )
    summary = create_summary(
        career.first_profile.id, session, text="Analista con foco en Salud Pública", lang="es"
    )
    track = career.first_track
    track.headline_en = "Senior Analytics Engineer"
    track.summary_es_id = summary.id
    session.flush()
    name = career.first_profile.display_name.split()[0]

    claims = _claims(
        session,
        career,
        f"certificado en Google Analytics por Coursera con {name}",
        "trabajé en Salud Pública como Senior Analytics Engineer",
    )

    assert claims == []


def test_a_bullets_first_word_is_a_sentence_start_not_a_name(session, career):
    """E3: the parts are joined with a newline, so the first word of each bullet — and of
    the headline — begins a sentence. The same word in mid-sentence is still a name."""
    assert _claims(session, career, "diseñé tableros mensuales", "Apliqué Python en reportes") == []
    assert _claims(session, career, "diseñé tableros mensuales", "usé Python y Apliqué reglas") == [
        "Apliqué"
    ]


def test_a_name_stored_nowhere_is_still_flagged(session, career):
    create_education(career.first_profile.id, session, institution="Universidad Nacional")

    assert _claims(session, career, "migré los flujos a Informatica en 2024") == [
        "Informatica",
        "2024",
    ]
