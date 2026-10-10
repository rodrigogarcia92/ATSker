"""Roles and bullets match on a punctuation-insensitive key (PRD F2.5, F10.3 step 3, E1).

A tailored CV writes `Results-Based` where the stored role says `Results - Based`; the
role and its bullets are still the same ones. `fold` is unchanged, so scoring, keywords
and the vocabulary hash do not move.
"""

import json
from datetime import date

import pytest

from src.attempt_flags import document_flags
from src.bullets import create_bullet
from src.extract import client as extract_client
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft
from src.ingest.merge import diff_draft
from src.models import ApplicationAttempt
from src.normalize.text import fold, match_key
from src.roles import create_role
from src.tracks import set_track_bullets
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes

STORED_TITLE = "Data Analyst & Results - Based Financing Specialist"
FILE_TITLE = "Data Analyst & Results-Based Financing Specialist"


def test_punctuation_and_spacing_around_it_do_not_change_the_key():
    assert match_key(STORED_TITLE) == match_key(FILE_TITLE)
    assert match_key("Data Analyst & Results–Based Financing Specialist") == match_key(FILE_TITLE)
    assert match_key("Results - Based") == "results based"


def test_operator_characters_survive():
    assert match_key("C++, C# & Análisis.") == "c++ c# & analisis"
    assert "c++" in match_key("Experiencia en C++")
    assert "c#" in match_key("Experiencia en C#")


def test_fold_is_untouched():
    assert fold("Results - Based") == "results - based"


def _role_draft(title: str, *bullets: str, start: str | None = None) -> ResumeDraft:
    return ResumeDraft(
        language="es",
        headline="Analista",
        roles=[
            DraftRole(
                employer="Empresa Demo 0",
                title=title,
                start_date=start,
                bullets=[DraftBullet(text=text) for text in bullets],
            )
        ],
    )


def test_import_matches_the_hyphen_variant_to_the_stored_role(session, career):
    role = create_role(
        career.first_profile.id,
        session,
        employer="Empresa Demo 0",
        title_es=STORED_TITLE,
        title_en=None,
    )
    session.commit()

    plan = diff_draft(career.first_profile.id, session, _role_draft(FILE_TITLE))

    (candidate,) = plan.roles
    assert candidate.label != "new"
    assert candidate.existing_id == role.id


def test_import_labels_a_bullet_that_differs_only_in_punctuation_unchanged(session, career):
    role = create_role(
        career.first_profile.id,
        session,
        employer="Empresa Demo 0",
        title_es=STORED_TITLE,
        title_en=None,
    )
    stored = create_bullet(
        career.first_profile.id,
        session,
        role_id=role.id,
        text_es="Construí pipelines en Google Cloud Platform, BigQuery y Looker",
        text_en=None,
        chips=[],
    )
    session.commit()

    plan = diff_draft(
        career.first_profile.id,
        session,
        _role_draft(
            FILE_TITLE, "Construí pipelines en Google Cloud Platform , BigQuery y Looker."
        ),
    )

    (bullet,) = plan.roles[0].bullets
    assert bullet.label == "unchanged"
    assert bullet.existing_id == stored.id


def test_the_title_flag_ignores_punctuation(session, career):
    create_role(
        career.first_profile.id,
        session,
        employer="Empresa Demo 0",
        title_es=STORED_TITLE,
        title_en=None,
    )
    session.commit()

    flags = document_flags(
        career.first_profile.id, session, draft=_role_draft(FILE_TITLE, "hice reportes")
    )

    assert flags["titles"] == []


def test_the_title_flag_still_reports_a_different_title(session, career):
    flags = document_flags(
        career.first_profile.id, session, draft=_role_draft("Directora de Nada", "hice reportes")
    )

    assert flags["titles"] == ["Directora de Nada"]


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def test_an_attempt_with_punctuation_variants_re_grades_nothing_and_keeps_the_years(
    client, session, career, provider
):
    login(client, career.first.email)
    role = career.first_role
    role.title_es = STORED_TITLE
    role.start_date = date(2018, 1, 1)
    role.end_date = date(2022, 1, 1)
    first = career.first_bullet
    first.text_es = "Reduje 30% el tiempo de reporte con Python , SQL"
    selected = [first.id]
    for text in ("Automaticé reportes - mensuales", "Capacité a equipos regionales (Lima)"):
        extra = create_bullet(
            career.first_profile.id,
            session,
            role_id=role.id,
            text_es=text,
            text_en=None,
            chips=[],
        )
        selected.append(extra.id)
    set_track_bullets(career.first_profile.id, session, career.first_track.id, selected)
    session.commit()
    application, analysis = analyzed_application(session, career, provider)
    before = len(provider.calls_for("EvidenceGrading"))

    file_bullets = (
        "Reduje 30% el tiempo de reporte con Python, SQL",
        "Automaticé reportes-mensuales",
        "Capacité a equipos regionales, Lima",
    )
    data = json.loads(resume_payload(*file_bullets))
    data["roles"][0].update(
        employer="Acme",
        title=STORED_TITLE.replace(" - ", "-"),
        start_date="2018-01",
        end_date="2022-01",
    )
    provider.answers["ResumeExtraction"] = json.dumps(data)

    client.post(
        f"/applications/{application.id}/attempts",
        files={"file": ("cv.docx", docx_bytes("Experiencia", *file_bullets), DOCX_TYPE)},
        follow_redirects=False,
    )

    attempt = session.query(ApplicationAttempt).one()
    assert attempt.status == "done"
    assert [row["temporary"] for row in attempt.report["bullets"]] == [False] * 3
    assert len(provider.calls_for("EvidenceGrading")) == before, "nothing is re-graded"
    assert (
        attempt.report["score"]["sub_scores"]["experience"]["detail"]["relevant_years"]
        == analysis.report["score"]["sub_scores"]["experience"]["detail"]["relevant_years"]
    )
    assert [row["by"] for row in attempt.report["role_matching"]] == ["employer_title"]
    assert attempt.report["flags"]["titles"] == []
