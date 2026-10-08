"""F7.3 Tier 1 / §12.5: "Proponer resumen" as a pop-up, summary only (queue K4).

The call returns a summary and its citations — no skills list — and accepting it never
touches the track's skills. Opening the pop-up is a GET that calls nothing; the button
inside is the POST. A failure says which of three things went wrong. Every provider here is
the fake one: no test pays for a call.
"""

import json
import logging
import re
from pathlib import Path

import httpx
import pytest

from src.extract import client as extract_client
from src.extract.prompts import SUMMARY_SKILLS_V2, SUMMARY_V3
from src.generate.validators import Sources, validate
from src.i18n import t
from src.models import ApplicationAttempt, LlmCall, Summary
from src.tracks import get_track, set_track_skills
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_analysis import text_of
from tests.unit.test_generation import Provider, proposal_payload, stored_application
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes

SRC = Path(__file__).resolve().parents[2] / "src"


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


def urls(application) -> tuple[str, str]:
    base = f"/applications/{application.id}/summary"
    return base, f"{base}/generate"


# --- the call: a summary and its citations, nothing else ---------------------------


def test_the_call_returns_a_summary_and_its_cites_only(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.post(urls(application)[1], data={"dialog": "1"}).text

    assert len(provider.calls) == 1
    asked = provider.calls[0]["response_format"]["json_schema"]
    assert asked["name"] == "SummaryOnly"
    assert set(asked["schema"]["properties"]) == {"summary", "cites"}, "no skills field to fill"
    assert 'name="payload"' in page
    payload = json.loads(
        re.search(r'name="payload" value="([^"]*)"', page).group(1).replace("&#34;", '"')
    )
    assert set(payload) == {"summary"} and set(payload["summary"]) == {"text", "cites"}


def test_the_prompt_is_summary_v3_with_the_skills_as_context_only():
    assert SUMMARY_V3.version == "summary_v3"
    assert "Never return a list of skills" in SUMMARY_V3.system
    assert "at most 15" not in SUMMARY_V3.system
    assert "Context only" in SUMMARY_V3.template, "the pool and the track's skills inform closure"
    assert "{pool}" in SUMMARY_V3.template and "{track_skills}" in SUMMARY_V3.template
    assert SUMMARY_SKILLS_V2.version == "summary_skills_v2", "kept, defined, unused"


def test_the_ledger_row_keeps_its_purpose_and_names_the_new_version(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)

    client.post(urls(application)[1], data={"dialog": "1"})

    rows = session.query(LlmCall).filter_by(purpose="generate_summary").all()
    assert [row.prompt_version for row in rows] == ["summary_v4"]
    from src.deletion import PERSONAL_PURPOSES

    assert "generate_summary" in PERSONAL_PURPOSES, "its answer is still blanked by Eliminar todo"


def test_the_old_v2_prompt_is_not_called_anywhere():
    users = [
        path.relative_to(SRC).as_posix()
        for path in SRC.rglob("*.py")
        if "SUMMARY_SKILLS_V2" in path.read_text(encoding="utf-8")
    ]

    assert users == ["extract/prompts.py"], "defined there and imported nowhere"


def test_the_validators_take_a_summary_with_no_skills_key():
    sources = Sources(bullets={"b1": "Automaticé el reporte."}, skills=frozenset({"python"}))

    clean = validate(
        {"summary": {"text": "Automaticé el reporte.", "cites": ["b1"]}},
        sources=sources,
        profile_id=None,
        session=None,
        kind="summary",
    )
    named = validate(
        {"summary": {"text": "Automaticé el reporte con python.", "cites": ["b1"]}},
        sources=Sources(
            bullets={"b1": "Automaticé el reporte."},
            skills=frozenset(),
            aliases={"python": "python"},
        ),
        profile_id=None,
        session=None,
        kind="summary",
    )

    assert clean == []
    assert [v.rule for v in named] == ["closure_missing"], "closure in the text is unchanged"


# --- accepting never writes the skills ---------------------------------------------


def test_accepting_leaves_the_tracks_skills_unchanged_even_if_an_old_page_posts_some(
    client, session, career, provider
):
    application = stored_application(session, career)
    set_track_skills(career.first_profile.id, session, career.first_track.id, ["python"])
    session.commit()
    login(client, career.first.email)

    accepted = client.post(
        urls(application)[0] + "/accept",
        data={
            "payload": proposal_payload(
                career, text="Automaticé el reporte con Python.", skills=["python", "sql"]
            ),
            "use_in_track": "on",
        },
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    session.expire_all()
    track = get_track(career.first_profile.id, session, career.first_track.id)
    assert track.skills == ["python"]
    assert session.query(Summary).filter_by(text="Automaticé el reporte con Python.").one()


def test_accepting_from_the_popup_returns_to_the_report_with_a_status_line(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)

    accepted = client.post(
        urls(application)[0] + "/accept",
        data={
            "payload": proposal_payload(career, text="Automaticé el reporte con Python."),
            "dialog": "1",
        },
        follow_redirects=False,
    )

    assert accepted.status_code == 303
    assert accepted.headers["location"] == f"/applications/{application.id}?summary_saved=1"
    page = client.get(accepted.headers["location"]).text
    status = re.search(r'<p id="summary-saved" role="status"[^>]*>(.*?)</p>', page, re.S)
    assert status and text_of(status.group(1)) == "Resumen guardado en tu material"
    assert "summary-saved" not in client.get(f"/applications/{application.id}").text, (
        "the line is for the redirect only"
    )


# --- the pop-up: opening is free, the button is the call ---------------------------


def test_opening_the_dialog_is_a_get_that_never_calls_the_provider(
    client, session, career, provider
):
    application = stored_application(session, career)
    login(client, career.first.email)

    opened = client.get(urls(application)[0] + "?dialog=1")

    assert opened.status_code == 200 and provider.calls == []
    assert "<html" not in opened.text, "a partial for the dialog's body, not a page"
    assert text_of(opened.text).count("Generar propuesta") == 1
    form = re.search(r'<form method="post" action="([^"]*)"[^>]*>', opened.text)
    assert form.group(1) == urls(application)[1]
    assert "data-dialog-form" in form.group(0), "posted in place by the shared dialog"
    assert 'name="dialog" value="1"' in opened.text
    assert "data-progress" in form.group(0) and "data-progress-status" in opened.text
    words = text_of(opened.text)
    assert "una llamada de pago" in words.lower() and "no cuesta nada" in words
    assert "1 bullets" in words or "bullets de «" in words, "what will be sent, in words"


def test_the_dialog_and_the_full_page_both_work(client, session, career, provider):
    application = stored_application(session, career)
    login(client, career.first.email)
    base, run = urls(application)

    page = client.get(base)
    popup = client.post(run, data={"dialog": "1"})
    full = client.post(run)

    assert "<html" in page.text and 'action="' + run + '"' in page.text
    assert "<html" not in popup.text and "<div data-dialog-dirty>" in popup.text
    assert "<html" in full.text and "<div data-dialog-dirty>" not in full.text
    for answer in (popup.text, full.text):
        assert "Analista de datos que automatizó el reporte con Python." in answer
        assert "Ahora" in answer and "Propuesta" in answer, "current beside the proposal"
        assert f'action="{base}/accept"' in answer
        assert 'name="use_in_track"' in answer
        assert "Habilidades clave nombradas" in text_of(answer), "the checklist row, not a block"
        form = answer.split("<form")[-1].replace("use_in_track", "")
        assert "skills" not in form, "no skills field"
    assert 'name="dialog" value="1"' in popup.text.split(f'action="{base}/accept"')[1]


def test_a_proposal_that_fails_a_validator_is_shown_without_an_accept_and_not_dirty(
    client, session, career, provider
):
    provider.answers["SummaryOnly"] = {
        "summary": "Reduje el reporte un 40% con Python.",
        "cites": [str(career.first_bullet.id)],
    }
    application = stored_application(session, career)
    login(client, career.first.email)

    popup = client.post(urls(application)[1], data={"dialog": "1"}).text

    assert "no pasó la validación" in popup and "40%" in popup
    assert "/summary/accept" not in popup
    assert "<div data-dialog-dirty>" not in popup, "nothing to confirm: it cannot be accepted"


@pytest.mark.parametrize("dialog", [{}, {"dialog": "1"}])
def test_a_foreign_application_is_a_404_in_every_form(client, session, career, provider, dialog):
    application = stored_application(session, career)
    login(client, career.second.email)
    base, run = urls(application)

    assert client.get(base + ("?dialog=1" if dialog else "")).status_code == 404
    assert client.post(run, data=dialog).status_code == 404
    assert client.post(base + "/accept", data={**dialog, "payload": "{}"}).status_code == 404
    assert provider.calls == []


# --- failures say why --------------------------------------------------------------


def run_and_read(client, application, caplog):
    caplog.set_level(logging.WARNING, logger="src.web.generation_errors")
    page = client.post(urls(application)[1], data={"dialog": "1"}).text
    return page, [r.getMessage() for r in caplog.records if r.name == "src.web.generation_errors"]


def test_no_model_configured_says_so_and_offers_no_button(
    client, session, career, provider, monkeypatch, caplog
):
    monkeypatch.setattr("src.web.routes.generate.model_configured", lambda: False)
    application = stored_application(session, career)
    login(client, career.first.email)

    opened = client.get(urls(application)[0] + "?dialog=1").text
    page, logs = run_and_read(client, application, caplog)

    for answer in (opened, page):
        assert t("generate.err.no_model", "es") in text_of(answer)
        assert "Generar propuesta" not in text_of(answer)
    assert provider.calls == []
    assert any("NoModelConfigured" in line and "generate_summary" in line for line in logs)


def test_an_unreachable_provider_says_so_and_the_button_comes_back(
    client, session, career, monkeypatch, caplog, test_settings
):
    def down(payload, api_key):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(extract_client, "_post", down)
    application = stored_application(session, career)
    login(client, career.first.email)

    page, logs = run_and_read(client, application, caplog)

    assert t("generate.err.provider", "es") in text_of(page)
    assert "Generar propuesta" in text_of(page), "a retry is possible"
    assert any("ProviderUnavailable" in line and "generate_summary" in line for line in logs)


def test_an_unusable_answer_says_so_and_never_logs_text(
    client, session, career, monkeypatch, caplog, test_settings
):
    secret = "Automaticé un reporte confidencial"

    def garbled(payload, api_key):
        return {
            "choices": [{"message": {"content": f"not json: {secret}"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": "0.000001"},
        }

    monkeypatch.setattr(extract_client, "_post", garbled)
    application = stored_application(session, career)
    login(client, career.first.email)

    page, logs = run_and_read(client, application, caplog)

    assert t("generate.err.unusable", "es") in text_of(page)
    assert any("StructuredOutputError" in line and "generate_summary" in line for line in logs)
    assert not any(secret in line for line in logs), "error class and purpose only"


def test_the_three_failures_read_differently():
    sentences = {
        t(key, "es")
        for key in ("generate.err.no_model", "generate.err.provider", "generate.err.unusable")
    }
    english = {
        t(key, "en")
        for key in ("generate.err.no_model", "generate.err.provider", "generate.err.unusable")
    }

    assert len(sentences) == 3 and len(english) == 3
    assert t("generate.failed", "es"), "the old sentence stays for the letter routes"


# --- the report's button -----------------------------------------------------------


def test_the_report_offers_a_pop_up_button_and_a_link_to_the_page(client, session, career):
    application = stored_application(session, career)
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    button = re.search(r"<button[^>]*data-dialog-url=[^>]*>(.*?)</button>", page, re.S)
    assert button and text_of(button.group(1)) == "Proponer resumen"
    assert f'data-dialog-url="/applications/{application.id}/summary?dialog=1"' in button.group(0)
    assert 'type="button"' in button.group(0)
    link = re.search(r'<a href="([^"]*)"[^>]*data-dialog-fallback', page)
    assert link and link.group(1) == f"/applications/{application.id}/summary"
    assert page.count('<dialog id="proposal-dialog"') == 1, "one shared dialog on the page"
    assert "y habilidades" not in t("generate.propose_summary", "es")
    assert "skills" not in t("generate.propose_summary", "en").lower()
    for key in ("generate.title", "generate.intro"):
        assert "abilidades" not in t(key, "es") and "skills" not in t(key, "en").lower()


def test_without_a_track_the_button_is_disabled_and_says_why(client, session, career):
    application = stored_application(session, career)
    application.track_id = None
    session.commit()
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text

    assert "data-dialog-url" not in page.split("§12.5")[0] and "summary?dialog=1" not in page
    disabled = re.search(r"<button[^>]*disabled[^>]*>(.*?)</button>", page, re.S)
    assert disabled and text_of(disabled.group(1)) == "Proponer resumen"
    assert 'aria-describedby="summary-no-track"' in disabled.group(0)
    assert "Elige una línea de carrera al analizar para proponer un resumen" in text_of(page)


def test_an_attempt_view_keeps_today_s_behaviour_and_shows_no_summary_button(
    client, session, career, monkeypatch, test_settings
):
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, stub)
    client.post(
        f"/applications/{application.id}/attempts",
        files={
            "file": ("cv.docx", docx_bytes("Experiencia", career.first_bullet.text_es), DOCX_TYPE)
        },
        follow_redirects=False,
    )
    attempt = session.query(ApplicationAttempt).one()

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text

    assert "Proponer resumen" not in raw and "summary-no-track" not in raw
