"""Gap notes after the report (PRD F12.3; F12.6 criteria 1, 3 and 4).

The analysis is stored as soon as the score exists, every gap's note empty and
`notes_status = "pending"`. The report page then sends one POST by itself; without
script its button sends the same one; a failure is stored as `"failed"` and the same
button becomes *Reintentar*. The provider is stubbed at `client._post`, so every count
below is a paid call that was, or was not, made.
"""

import json
import uuid
from decimal import Decimal

import httpx
import pytest

from src.analysis import analyze, interpret_stored_gaps
from src.applications import create_application, get_application
from src.extract import client as extract_client
from src.models import Application, LlmCall
from tests.conftest import login
from tests.unit.attempt_support import POSTING, AttemptProvider
from tests.unit.cv_support import analysis_form

NOTE = "Machine learning está mencionado sin una historia."


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(bullet_id=str(career.first_bullet.id))
    # One gap (machine learning, nice-to-have, level 0) and the two things that always
    # travel with the notes: the single warning and what was not found.
    stub.answers["GapInterpretation"] = json.dumps(
        {
            "gaps": [
                {"requirement": "machine learning", "blocking": False, "interpretation": NOTE}
            ],
            "warning": {
                "text": "Salto hacia banca privada",
                "handling": "Llévalo como transferencia de método analítico.",
            },
            "not_found": "No hay historias sobre despliegue de modelos.",
        }
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def submit(client, session, career) -> str:
    """Analyse the posting the way the page does, and return the report's own URL."""
    posted = client.post(
        "/analyze",
        data=analysis_form(session, career, jd_text=POSTING),
        follow_redirects=False,
    )
    assert posted.status_code == 303
    return posted.headers["location"]


def fill(client, location: str):
    """The POST the report's section sends once it is on screen."""
    return client.post(f"{location}/gap-notes", headers={"X-Requested-With": "fetch"})


def stored(session, application_id: str | None = None) -> Application:
    session.expire_all()
    if application_id is not None:
        application = session.get(Application, uuid.UUID(application_id))
        assert application is not None
        return application
    (application,) = session.query(Application).order_by(Application.created_at, Application.id)
    return application


def test_the_analysis_is_stored_before_its_gap_notes_exist(client, session, career, provider):
    """F12.6.1: the report appears before the notes, and nothing is paid for them yet."""
    login(client, career.first.email)

    location = submit(client, session, career)

    block = stored(session).report["gaps"]
    assert block["notes_status"] == "pending"
    assert [row["requirement"] for row in block["gaps"]] == ["machine learning"]
    assert [row["interpretation"] for row in block["gaps"]] == [""]
    assert block["warning"] == {"text": "", "handling": ""}
    assert provider.calls_for("GapInterpretation") == []
    assert session.query(LlmCall).filter(LlmCall.purpose == "gap_interpret").count() == 0

    page = client.get(location).text
    assert f'action="{location}/gap-notes"' in page, "the section carries the POST it sends"
    assert "Explicar brechas" in page


def test_the_page_post_fills_the_notes_and_stores_them(client, session, career, provider):
    login(client, career.first.email)
    location = submit(client, session, career)

    response = fill(client, location)

    assert response.status_code == 200
    assert 'id="before"' in response.text, "the answer is the section that replaces itself"
    assert NOTE in response.text
    assert "Salto hacia banca privada" in response.text
    assert "No hay historias sobre despliegue de modelos." in response.text
    assert "data-gap-notes" not in response.text, "there is nothing left to ask for"

    block = stored(session).report["gaps"]
    assert block["notes_status"] == "ready"
    assert block["gaps"][0]["interpretation"].startswith(NOTE)
    assert block["warning"]["handling"].startswith("Llévalo como transferencia")
    assert block["not_found"].startswith("No hay historias")
    assert len(provider.calls_for("GapInterpretation")) == 1

    page = client.get(location).text
    assert NOTE in page, "the report shows what it stored"
    assert "Explicar brechas" not in page
    assert f'action="{location}/gap-notes"' not in page, "nothing left to ask for"


def test_the_notes_call_is_recorded_beside_the_analysis_cost(client, session, career, provider):
    """F12.3, F12.4: the deferred call is part of the report's cost — and only of the cost."""
    login(client, career.first.email)
    location = submit(client, session, career)
    before = stored(session).report["llm"]
    assert "deferred" not in before

    fill(client, location)

    after = stored(session).report["llm"]
    (call,) = after["deferred"]["calls"]
    assert call["purpose"] == "gap_interpret"
    assert call["cost_usd"] == "0.000123"
    assert call["latency_ms"] is not None, "the call names what it took, like every other"
    assert after["deferred"]["cost_usd"] == "0.000123"
    assert after["calls"] == before["calls"], "the analysis's own calls never move"
    assert after["cost_usd"] == before["cost_usd"] == "0.000369"
    assert after["wall_ms"] == before["wall_ms"], "the report appeared before this call"

    page = client.get(location).text
    assert "4 · $0.000492" in page, "the line adds the notes to the three analysis calls"


def test_notes_already_there_are_returned_and_never_paid_again(client, session, career, provider):
    """F12.6.4: the POST on a report that already has its notes makes no call."""
    login(client, career.first.email)
    location = submit(client, session, career)
    fill(client, location)

    again = fill(client, location)

    assert again.status_code == 200
    assert NOTE in again.text
    assert len(provider.calls_for("GapInterpretation")) == 1
    assert session.query(LlmCall).filter(LlmCall.purpose == "gap_interpret").count() == 1
    assert len(stored(session).report["llm"]["deferred"]["calls"]) == 1, "no second entry"


def test_without_script_the_button_posts_and_lands_on_the_report(client, session, career, provider):
    login(client, career.first.email)
    location = submit(client, session, career)

    response = client.post(f"{location}/gap-notes", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"].startswith(location)
    assert stored(session).report["gaps"]["notes_status"] == "ready"
    assert "Explicar brechas" not in client.get(location).text


def test_a_failed_call_is_stored_as_failed_and_the_section_offers_a_retry(
    client, session, career, provider, monkeypatch
):
    login(client, career.first.email)
    location = submit(client, session, career)

    def failing(payload, api_key):
        if payload["response_format"]["json_schema"]["name"] == "GapInterpretation":
            raise httpx.ConnectError("the provider is down")
        return provider(payload, api_key)

    with monkeypatch.context() as patch:
        patch.setattr(extract_client, "_post", failing)
        response = fill(client, location)

    assert response.status_code == 200
    assert "Reintentar" in response.text
    assert "No se pudieron explicar las brechas." in response.text
    report = stored(session).report
    assert report["gaps"]["notes_status"] == "failed"
    assert [row["interpretation"] for row in report["gaps"]["gaps"]] == [""]
    assert "deferred" not in report["llm"], "a failure is never recorded as a call"

    retried = fill(client, location)

    assert "Reintentar" not in retried.text
    assert NOTE in retried.text
    assert stored(session).report["gaps"]["notes_status"] == "ready"
    assert len(provider.calls_for("GapInterpretation")) == 1, "the failed attempt paid nothing"


def test_another_profiles_application_is_a_404_and_pays_nothing(client, session, career, provider):
    """A foreign id is not found, and not found never reaches the provider."""
    theirs = create_application(
        career.second_profile.id,
        session,
        jd_text=POSTING,
        jd_hash="0" * 64,
        report={"gaps": {"gaps": [], "notes_status": "pending"}},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    session.commit()
    login(client, career.first.email)

    response = fill(client, f"/applications/{theirs.id}")

    assert response.status_code == 404
    assert provider.calls == []


def test_a_second_analysis_of_the_same_posting_pays_for_the_notes_once(
    client, session, career, provider
):
    """F12.6.3: a cached re-analysis makes zero calls and shows its notes at once."""
    login(client, career.first.email)
    first = submit(client, session, career)
    fill(client, first)
    paid = len(provider.calls)

    second = submit(client, session, career)

    assert len(provider.calls) == paid, "extraction, queries and grading come from the cache"

    response = fill(client, second)

    assert len(provider.calls) == paid, "the same gaps under the same prompt are one cache entry"
    assert NOTE in response.text
    application = get_application(
        career.first_profile.id, session, second.rsplit("/", 1)[-1]
    )
    assert application is not None
    assert application.report["gaps"]["notes_status"] == "ready"


def test_a_report_stored_with_its_notes_shows_no_button_and_asks_for_nothing(
    client, session, career, provider
):
    """A report stored before F12 carries its notes and no status at all."""
    login(client, career.first.email)
    analysis = analyze(career.first_profile.id, session, jd_text=POSTING, track=career.first_track)
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=POSTING,
        jd_hash=analysis.jd_hash,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    paid = len(provider.calls)

    page = client.get(f"/applications/{application.id}").text

    assert NOTE in page
    assert "Explicar brechas" not in page
    assert f'action="/applications/{application.id}/gap-notes"' not in page

    again = fill(client, f"/applications/{application.id}")

    assert NOTE in again.text
    assert len(provider.calls) == paid


def test_a_report_with_no_status_is_never_paid_for(session, career, provider):
    """An attempt detects its gaps and never interprets them (F10.3)."""
    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, notes="none", track=career.first_track
    )
    paid = len(provider.calls)

    assert "notes_status" not in analysis.report["gaps"]
    assert interpret_stored_gaps(career.first_profile.id, session, analysis.report) is None
    assert len(provider.calls) == paid
