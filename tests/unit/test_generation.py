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
from src.bullets import get_bullet, list_bullets
from src.extract import client as extract_client
from src.models import Bullet, BulletRevision, Summary, TrackBullet
from src.stories import get_story
from src.tracks import get_track, set_track_skills
from tests.conftest import login


class Provider:
    """Answers one generated-text schema per call, priced like a real call."""

    def __init__(self, answers: dict | None = None):
        self.calls: list[dict] = []
        self.answers = {
            "SummaryOnly": {"summary": "Automaticé el reporte con Python.", "cites": []},
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
            "SummaryOnly": {
                "summary": "Analista de datos que automatizó el reporte con Python.",
                "cites": [str(career.first_bullet.id)],
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
        else [
            {
                "requirement": "python",
                "must_have": True,
                "level": 3,
                "basis": "direct",
                "bullet_id": bullet_id,
                "bullet_text": career.first_bullet.text_es,
            }
        ],
        "score": {
            "capped": 40,
            "uncapped": 62,
            "cap": 40,
            "cap_reason": "invisible_text",
            "unavailable": {},
            "sub_scores": {},
            "effective_weights": {},
            "effective_weights_hash": "sha256:0",
        },
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
    career, *, text: str, skills: list[str] | None = None, cites: list[str] | None = None
) -> str:
    """A proposal as the form carries it. `skills` is what an older page still posts."""
    payload: dict = {"summary": {"text": text, "cites": cites or [str(career.first_bullet.id)]}}
    if skills is not None:
        payload["skills"] = skills
    return json.dumps(payload)


def test_the_proposal_is_shown_as_a_diff(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)
    url = f"/applications/{application.id}/summary"

    button = client.get(url)
    assert button.status_code == 200
    assert f'action="{url}/generate"' in button.text, "a GET offers the call, it does not make it"

    page = client.post(f"{url}/generate").text
    assert "Ahora" in page and "Propuesta" in page, "both sides of the diff"
    assert "Analista de datos que automatizó el reporte con Python." in page
    assert f'action="{url}/accept"' in page


def test_accepting_writes_the_pool_row_and_the_track_slot_and_never_the_skills(
    client, session, career, provider
):
    application = stored_application(session, career)
    set_track_skills(career.first_profile.id, session, career.first_track.id, [])
    session.commit()
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
    assert track.skills == [], "an old page's skills field is ignored: the list is not replaced"
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


def test_a_generated_proposal_that_fails_a_validator_is_shown_marked_and_editable(
    client, session, career, provider
):
    """The proposal is shown with its findings in an editable text area (F7.3 (b), P5).

    It used to carry no accept control; now the user can edit it, and the server still
    refuses whatever does not pass (see test_summary_editable)."""
    provider.answers["SummaryOnly"] = {
        "summary": "Automaticé el reporte con Kubernetes.",
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career)
    login(client, career.first.email)

    url = f"/applications/{application.id}/summary"
    page = client.post(f"{url}/generate").text

    assert "no pasa la validación" in page and "Kubernetes" in page
    assert '<textarea id="proposal-text"' in page
    assert f'action="{url}/accept"' in page


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


# --- N7.3: Tier 3a, one bullet rephrased for the posting ---------------------------


REPHRASE = "Automaticé el reporte con Python y reduje el tiempo un 30%."


def rephrase_url(application, bullet_id):
    return f"/applications/{application.id}/bullets/{bullet_id}/rephrase"


def test_the_report_links_each_cited_bullet_to_a_rephrase(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert rephrase_url(application, career.first_bullet.id) in page
    assert "Reformular para este aviso" in page


def test_a_rephrase_is_proposed_and_shown(client, session, career, provider):
    provider.answers["BulletRephrase"] = {
        "text": REPHRASE,
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career)
    login(client, career.first.email)

    url = rephrase_url(application, career.first_bullet.id)

    assert f'action="{url}/generate"' in client.get(url).text, "a GET only offers the call"
    page = client.post(f"{url}/generate").text

    assert REPHRASE in page
    assert f'action="{url}/accept"' in page


def test_accepting_a_rephrase_writes_a_revision_and_keeps_the_other_column(
    client, session, career, provider
):
    provider.answers["BulletRephrase"] = {
        "text": REPHRASE,
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career)
    login(client, career.first.email)

    accepted = client.post(
        f"{rephrase_url(application, career.first_bullet.id)}/accept",
        data={"payload": json.dumps({"text": REPHRASE, "cites": [str(career.first_bullet.id)]})},
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    session.expire_all()
    bullet = get_bullet(career.first_profile.id, session, career.first_bullet.id)
    assert bullet.text_es == REPHRASE
    assert bullet.text_en is None, "the other language column is untouched"
    revision = session.query(BulletRevision).one()
    assert revision.text_es == "Reduje 30% el tiempo de reporte con Python"
    assert revision.text_en is None


def test_a_rephrase_with_an_invented_metric_is_refused(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)
    tampered = "Automaticé el reporte y reduje el tiempo un 55%."

    refused = client.post(
        f"{rephrase_url(application, career.first_bullet.id)}/accept",
        data={"payload": json.dumps({"text": tampered, "cites": [str(career.first_bullet.id)]})},
    )

    assert refused.status_code == 200
    assert "55%" in refused.text
    session.expire_all()
    assert session.query(BulletRevision).count() == 0
    assert get_bullet(career.first_profile.id, session, career.first_bullet.id).text_es == (
        "Reduje 30% el tiempo de reporte con Python"
    )


def test_a_bullet_without_text_in_the_posting_language_is_a_suggested_translation(
    client, session, career, provider
):
    provider.answers["BulletRephrase"] = {
        "text": "Automated reporting with Python, cutting turnaround by 30%.",
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career, language="en")
    login(client, career.first.email)

    url = rephrase_url(application, career.first_bullet.id)
    page = client.post(f"{url}/generate").text

    assert "Sugerencia de traducción" in page


# --- N7.4: Tier 3b, bullets a story supports ---------------------------------------


STORY_BULLET = "Automaticé el reporte manual y lo llevé a un proceso continuo."


def story_bullets_url(story):
    return f"/stories/{story.id}/bullets"


def test_story_bullets_are_proposed_as_reviewable_candidates(client, session, career, provider):
    provider.answers["StoryBullets"] = {
        "bullets": [
            {
                "text": STORY_BULLET,
                "story_id": str(career.first_story.id),
                "role_id": str(career.first_role.id),
            }
        ]
    }
    login(client, career.first.email)

    url = story_bullets_url(career.first_story)

    assert f'action="{url}/generate"' in client.get(url).text, "a GET only offers the call"
    page = client.post(f"{url}/generate", data={"lang": "es"}).text

    assert STORY_BULLET in page
    assert f'action="{url}/accept"' in page
    assert 'name="chips"' in page, "the candidate carries typed chips (F2.9)"


def test_accepting_a_story_bullet_creates_it_with_its_provenance(client, session, career, provider):
    login(client, career.first.email)

    accepted = client.post(
        f"{story_bullets_url(career.first_story)}/accept",
        data={
            "text": STORY_BULLET,
            "role_id": str(career.first_role.id),
            "chips": "python, cobalto",
            "lang": "es",
        },
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    session.expire_all()
    created = [
        bullet
        for bullet in list_bullets(career.first_profile.id, session, active_only=False)
        if bullet.text_es == STORY_BULLET
    ]
    assert len(created) == 1
    bullet = created[0]
    assert bullet.source_story_id == career.first_story.id
    assert bullet.role_id == career.first_role.id
    assert bullet.skills == ["python"]
    assert bullet.pending_terms == ["cobalto"], "an unknown chip is kept, not dropped"
    assert session.query(TrackBullet).count() == 2, "the new bullet joins no track"


def test_a_story_bullet_with_an_invented_number_cannot_be_accepted(
    client, session, career, provider
):
    login(client, career.first.email)
    before = session.query(Bullet).count()

    refused = client.post(
        f"{story_bullets_url(career.first_story)}/accept",
        data={
            "text": "Reduje un 40% el trabajo manual.",
            "role_id": str(career.first_role.id),
            "chips": "",
            "lang": "es",
        },
    )

    assert refused.status_code == 200
    assert "40%" in refused.text
    assert session.query(Bullet).count() == before


def test_a_role_of_another_profile_is_refused(client, session, career, provider):
    login(client, career.first.email)

    response = client.post(
        f"{story_bullets_url(career.first_story)}/accept",
        data={
            "text": STORY_BULLET,
            "role_id": str(career.second_role.id),
            "chips": "",
            "lang": "es",
        },
    )

    assert response.status_code == 404


def test_accepting_a_story_bullet_leaves_the_story_unchanged(client, session, career, provider):
    login(client, career.first.email)
    before = (career.first_story.title, career.first_story.body)

    client.post(
        f"{story_bullets_url(career.first_story)}/accept",
        data={
            "text": STORY_BULLET,
            "role_id": str(career.first_role.id),
            "chips": "",
            "lang": "es",
        },
        follow_redirects=False,
    )

    session.expire_all()
    story = get_story(career.first_profile.id, session, career.first_story.id)
    assert (story.title, story.body) == before


# --- F.0: a paid call is a POST, and only a POST -----------------------------------


def test_a_get_makes_no_provider_call_and_the_post_does(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)

    client.get(f"/applications/{application.id}/summary")
    client.get(rephrase_url(application, career.first_bullet.id))
    client.get(story_bullets_url(career.first_story))
    assert provider.calls == [], "a GET never pays for a call"

    client.post(f"/applications/{application.id}/summary/generate")
    assert len(provider.calls) == 1, "the POST is what calls the provider"


def test_the_generate_posts_refuse_another_profiles_ids(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.second.email)

    assert (
        client.post(f"/applications/{application.id}/summary/generate").status_code == 404
    )
    assert (
        client.post(
            f"/applications/{application.id}/bullets/{career.first_bullet.id}/rephrase/generate"
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/stories/{career.first_story.id}/bullets/generate", data={"lang": "es"}
        ).status_code
        == 404
    )


def test_the_proposal_page_groups_violations_and_names_both_closure_failures(
    client, session, career, provider
):
    """`python` is in the pool but ungraded (unevidenced); `machine learning` is not (missing).

    The skills are named in the summary's own text: there is no skills block any more."""
    provider.answers["SummaryOnly"] = {
        "summary": "Automaticé el reporte con Python y machine learning.",
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career, grades=[])
    login(client, career.first.email)

    page = client.post(f"/applications/{application.id}/summary/generate").text

    assert "Habilidades que no están en tus datos (1)" in page
    assert "no se muestran con nivel 2 o mejor" in page
    assert "«machine learning»" in page and "«python»" in page


def test_the_summary_prompt_is_versioned_and_states_the_pool_rule():
    from src.extract.prompts import SUMMARY_SKILLS_V1, SUMMARY_SKILLS_V2

    assert SUMMARY_SKILLS_V1.version == "summary_skills_v1", "old reports keep citing V1"
    assert SUMMARY_SKILLS_V2.version == "summary_skills_v2"
    assert "at most 15" in SUMMARY_SKILLS_V2.system
    assert "at most 15" not in SUMMARY_SKILLS_V1.system
    assert SUMMARY_SKILLS_V2.template == SUMMARY_SKILLS_V1.template


def test_generating_uses_the_v4_prompt_and_asks_for_no_skills_list(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)

    client.post(f"/applications/{application.id}/summary/generate")

    sent = json.dumps(provider.calls[-1])
    assert "at most 15" not in sent, "V2's skills-list rule is gone"
    assert "Never return a list of skills" in sent
