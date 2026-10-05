"""The modal's upload area and "Nuevo intento (N de 10)" (PRD F10.4, V2).

Before the first attempt the modal opens on the upload; once there is a result the upload
is hidden and the end of the result offers a primary button that brings it back, cleared.
N is the counted attempts plus one (failed attempts do not count), so at the limit there is no
button and the limit text takes its place. A running attempt offers neither.
"""

import re

import pytest

from src.attempts import MAX_ATTEMPTS
from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_ingest_routes import plain


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _application(session, career, provider):
    """A stored analysis, so the report page renders; the attempts are rows beside it."""
    application, _analysis = analyzed_application(session, career, provider)
    return application


def _attempt(session, career, application, number, status="done") -> ApplicationAttempt:
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=number,
        status=status,
        file_sha256=f"{number:064d}",
        prompt_versions={},
        report={"draft": {"language": "es"}, "flags": {}} if status == "done" else None,
        error="No se pudo leer" if status == "failed" else None,
    )
    session.add(attempt)
    session.commit()
    return attempt


def _upload_tag(raw: str) -> str:
    start = raw.index('id="attempt-upload"')
    return raw[start : raw.index(">", start)]


def test_with_no_attempts_the_upload_shows_and_says_probar_este_archivo(
    client, session, career, provider
):
    login(client, career.first.email)
    application = _application(session, career, provider)

    raw = client.get(f"/applications/{application.id}").text

    assert "hidden" not in _upload_tag(raw)
    submit = raw[raw.index('id="attempt-submit"') :]
    assert "Probar este archivo" in plain(submit[: submit.index("</button>")])


def test_the_submit_label_is_translated(client, session, career, provider):
    from src.i18n import t

    assert t("attempt.form.submit", "en") == "Test this file"
    assert t("attempt.new", "en", n=2, max=10) == "New attempt (2 of 10)"


def test_with_a_done_attempt_the_upload_is_hidden_and_the_result_offers_nuevo_intento(
    client, session, career, provider
):
    login(client, career.first.email)
    application = _application(session, career, provider)
    attempt = _attempt(session, career, application, 1)

    page = client.get(f"/applications/{application.id}").text
    assert "hidden" in _upload_tag(page).replace('id="attempt-upload"', "")

    result = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    button = result[result.index('id="attempt-new"') :]
    button = button[: button.index("</button>")]
    assert "Nuevo intento (2 de 10)" in plain(button)
    assert not re.search(r"\sdisabled[\s>]", button.split(">")[0])
    assert "bg-link" in button, "the primary style"
    # After the actions and before the attempts list.
    assert result.index("/discard") < result.index('id="attempt-new"')
    assert result.index('id="attempt-new"') < result.rindex("data-attempt-url=")


def test_a_failed_attempt_also_offers_a_way_back_to_the_upload(client, session, career, provider):
    login(client, career.first.email)
    application = _application(session, career, provider)
    attempt = _attempt(session, career, application, 1, status="failed")

    page = client.get(f"/applications/{application.id}").text
    result = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text

    assert "hidden" in _upload_tag(page).replace('id="attempt-upload"', "")
    assert 'id="attempt-new"' in result
    # A failure does not consume one of the ten: the next attempt is still the first.
    assert "Nuevo intento (1 de 10)" in plain(result)


def test_at_the_limit_there_is_no_button_and_the_limit_text_takes_its_place(
    client, session, career, provider
):
    login(client, career.first.email)
    application = _application(session, career, provider)
    for number in range(1, MAX_ATTEMPTS + 1):
        last = _attempt(session, career, application, number)
    _attempt(session, career, application, MAX_ATTEMPTS + 1, status="failed")

    result = client.get(f"/applications/{application.id}/attempts/{last.id}").text

    assert 'id="attempt-new"' not in result, "ten counted attempts and one failure: no button"
    assert "Nuevo intento" not in plain(result), "and never an 11th, 12th… in its label"
    assert "Este análisis ya tiene 10 intentos, que es el máximo." in plain(result)
    assert 'id="attempt-new-limit"' in result


def test_failed_attempts_do_not_move_the_number(client, session, career, provider):
    login(client, career.first.email)
    application = _application(session, career, provider)
    for number in (1, 2, 3):
        last = _attempt(session, career, application, number)
    for number in (4, 5):
        _attempt(session, career, application, number, status="failed")

    result = client.get(f"/applications/{application.id}/attempts/{last.id}").text

    assert "Nuevo intento (4 de 10)" in plain(result), "3 counted + 2 failed"


def test_the_label_never_exceeds_the_limit_while_the_button_is_offered(
    client, session, career, provider
):
    login(client, career.first.email)
    application = _application(session, career, provider)
    for number in range(1, MAX_ATTEMPTS):
        last = _attempt(session, career, application, number)

    result = client.get(f"/applications/{application.id}/attempts/{last.id}").text

    assert "Nuevo intento (10 de 10)" in plain(result), "the last one is still allowed"


def test_a_running_attempt_offers_neither_the_upload_nor_the_button(
    client, session, career, provider
):
    login(client, career.first.email)
    application = _application(session, career, provider)
    attempt = _attempt(session, career, application, 1, status="running")

    page = client.get(f"/applications/{application.id}").text
    result = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text

    assert 'data-status="running"' in result
    assert 'id="attempt-new"' not in result
    assert "hidden" in _upload_tag(page).replace('id="attempt-upload"', "")


def test_the_script_reopens_the_upload_cleared_and_focused(client, session, career, provider):
    login(client, career.first.email)
    application = _application(session, career, provider)

    raw = client.get(f"/applications/{application.id}").text
    handler = raw[raw.index('closest("#attempt-new")') :]
    handler = handler[: handler.index("file.focus();")]

    assert "upload.hidden = false" in handler
    assert 'file.value = ""' in handler
    assert 'new Event("change"' in handler, "the drop zone empties its file row on change"
    assert "upload.scrollIntoView" in handler
    assert "file.focus();" in raw[raw.index('closest("#attempt-new")') :]
    # While a run is in flight the upload and the button are put away, and a refusal
    # brings the upload back for a retry.
    busy = raw[raw.index("function setBusy") :]
    busy = busy[: busy.index("function showError")]
    assert "upload.hidden = busy" in busy
    assert re.search(r"again\.hidden = busy", busy)
    assert "upload.hidden = resultShown" in raw
