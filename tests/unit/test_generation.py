"""F7.3's generated text over HTTP: propose, diff, accept, refuse (N7.2).

The provider is stubbed at `extract_client._post`, so the whole path runs offline:
the proposal is built from the track's own bullets, shown as a diff, and accepted
only after the validators run again against the database — the form text is never
trusted.
"""

import json
from decimal import Decimal

import pytest

from src.applications import create_application
from src.extract import client as extract_client
from src.models import Summary
from src.tracks import get_track
from tests.conftest import login


class Provider:
    """Answers one generated-text schema per call, priced like a real call."""

    def __init__(self, answers: dict | None = None):
        self.calls: list[dict] = []
        self.answers = {
            "SummarySkills": {
                "summary": "Automaticé el reporte con Python.",
                "cites": [],
                "skills": ["python"],
            },
            "BulletRephrase": {"text": "Automaticé el reporte con Python.", "cites": []},
            "StoryBullets": {"bullets": []},
        }
        self.answers.update(answers or {})

    def __call__(self, payload: dict, api_key: str) -> dict:
        self.calls.append(payload)
        name = payload["response_format"]["json_schema"]["name"]
        return {
            "choices": [{"message": {"content": json.dumps(self.answers[name])}}],
            "usage": {"prompt_tokens": 800, "completion_tokens": 120, "cost": "0.000042"},
        }


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(
        {
            "SummarySkills": {
                "summary": "Automaticé el reporte con Python.",
                "cites": [str(career.first_bullet.id)],
                "skills": ["python"],
            }
        }
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def stored_application(session, career, *, language: str = "es", grades: list | None = None):
    bullet_id = str(career.first_bullet.id)
    # The track's skills list is a subset of the profile's pool (F4.1), so an accepted
    # block can only keep pool canonicals; give the profile the one the stub proposes.
    career.first_profile.skills = ["python"]
    report = {
        "jd": {
            "language": language,
            "title": "Analista de datos",
            "seniority": "mid",
            "must_have": ["python"],
            "nice_to_have": [],
            "raw_keywords": [],
            "hard_requirements": [],
        },
        "grades": grades
        if grades is not None
        else [{"requirement": "python", "must_have": True, "level": 3, "bullet_id": bullet_id}],
        "score": {},
        "llm": {"calls": []},
    }
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Analista de datos con Python",
        jd_hash="sha256:generation",
        report=report,
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal(0),
        track_id=career.first_track.id,
    )
    session.commit()
    return application


def proposal_payload(
    career, *, text: str, skills: list[str], cites: list[str] | None = None
) -> str:
    return json.dumps(
        {
            "summary": {"text": text, "cites": cites or [str(career.first_bullet.id)]},
            "skills": skills,
        }
    )


def test_the_proposal_is_shown_as_a_diff(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)

    response = client.get(f"/applications/{application.id}/summary")

    assert response.status_code == 200
    page = response.text
    assert "Ahora" in page and "Propuesta" in page, "both sides of the diff"
    assert "Automaticé el reporte con Python." in page
    assert f'action="/applications/{application.id}/summary/accept"' in page


def test_accepting_writes_the_pool_row_the_track_skills_and_the_track_slot(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)

    accepted = client.post(
        f"/applications/{application.id}/summary/accept",
        data={
            "payload": proposal_payload(
                career, text="Automaticé el reporte con Python.", skills=["python"]
            ),
            "use_in_track": "on",
        },
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    assert accepted.headers["location"] == f"/tracks/{career.first_track.id}"
    session.expire_all()
    summary = session.query(Summary).filter_by(text="Automaticé el reporte con Python.").one()
    assert summary.lang == "es"
    track = get_track(career.first_profile.id, session, career.first_track.id)
    assert track.skills == ["python"]
    assert track.summary_es_id == summary.id


def test_accepting_without_the_box_leaves_the_track_summary_alone(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)
    before = session.query(Summary).count()

    client.post(
        f"/applications/{application.id}/summary/accept",
        data={
            "payload": proposal_payload(
                career, text="Automaticé el reporte con Python.", skills=["python"]
            )
        },
        follow_redirects=False,
    )

    session.expire_all()
    assert session.query(Summary).count() == before + 1, "the summary still joins the pool"
    track = get_track(career.first_profile.id, session, career.first_track.id)
    assert track.summary_es_id is None, "the box is what puts it in the track"


def test_a_tampered_skill_is_refused_on_accept(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)
    before = session.query(Summary).count()

    refused = client.post(
        f"/applications/{application.id}/summary/accept",
        data={
            "payload": proposal_payload(
                career,
                text="Automaticé el reporte con Python y Tableau.",
                skills=["python", "tableau"],
            )
        },
    )

    assert refused.status_code == 200
    assert "no pasó la validación" in refused.text
    assert session.query(Summary).count() == before, "nothing is stored on a refusal"


def test_a_tampered_number_is_refused_on_accept(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)
    before = session.query(Summary).count()

    refused = client.post(
        f"/applications/{application.id}/summary/accept",
        data={
            "payload": proposal_payload(
                career, text="Reduje el reporte un 40% con Python.", skills=["python"]
            )
        },
    )

    assert refused.status_code == 200
    assert "40%" in refused.text, "the offending text is shown"
    assert session.query(Summary).count() == before


def test_a_generated_proposal_that_fails_a_validator_cannot_be_accepted(
    client, session, career, provider
):
    """The proposal is shown, marked, and there is no accept control (F7.3)."""
    provider.answers["SummarySkills"] = {
        "summary": "Automaticé el reporte con Kubernetes.",
        "cites": [str(career.first_bullet.id)],
        "skills": ["python", "kubernetes"],
    }
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}/summary").text

    assert "no pasó la validación" in page
    assert f'action="/applications/{application.id}/summary/accept"' not in page


def test_another_profiles_application_is_a_404(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.second.email)

    assert client.get(f"/applications/{application.id}/summary").status_code == 404
    assert (
        client.post(
            f"/applications/{application.id}/summary/accept",
            data={"payload": proposal_payload(career, text="x", skills=[])},
        ).status_code
        == 404
    )
