"""The attempt modal and the result's content order (PRD F10.1, F10.4, C.1).

The analysis page carries a native `<dialog>` with the upload and the list; a finished
attempt's partial renders F10.4's order (Job Match against the ceiling, the delta vs
the analysis with the stability band, the sub-scores with their ceilings, what changed,
what is new, what is left, the cost and the full-report link); a `running` partial
carries the URL the modal polls; and the attempt's own full report is read-only.
"""

import re
from pathlib import Path

import pytest

from src.extract import client as extract_client
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes, plain


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


def _run(client, session, career, provider):
    login(client, career.first.email)
    application, analysis = analyzed_application(session, career, provider)
    upload(client, application.id, docx_bytes("Experiencia", career.first_bullet.text_es))
    attempt = session.query(ApplicationAttempt).one()
    return application, analysis, attempt


def test_the_analysis_page_carries_the_modal(client, session, career, provider):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    raw = client.get(f"/applications/{application.id}").text

    assert "<dialog id=\"attempt-modal\"" in raw
    assert 'enctype="multipart/form-data"' in raw
    assert "startPoll" in raw, "the polling script is present"
    assert "showModal" in raw, "focus trapping and Escape come from the platform"


def test_a_running_attempt_polls_and_a_finished_one_shows_the_result(
    client, session, career, provider
):
    application, _analysis, attempt = _run(client, session, career, provider)

    status = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    assert f'data-attempt-url="/applications/{application.id}/attempts/{attempt.id}"' in status
    assert 'data-status="done"' in status
    text = plain(status)
    assert "Qué cambió" in text
    assert "Nuevo en este documento" in text
    assert "Qué queda" in text
    assert "Ver el informe completo" in text
    assert "Componentes" in text or "Habilidades" in text


def test_the_delta_reads_flat_within_the_stability_band(client, session, career, provider):
    """An unchanged export scores what the analysis scored, so the delta is zero."""
    application, _analysis, attempt = _run(client, session, career, provider)

    text = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    assert "vs. análisis del puesto" in text
    assert "sin cambio significativo" in text


def test_the_attempt_report_is_read_only(client, session, career, provider):
    application, _analysis, attempt = _run(client, session, career, provider)

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text
    text = plain(raw)

    assert "Intento 1 — informe completo" in text
    assert "Volver al análisis" in text
    # No action that acts on the analysis appears.
    assert "Analizar otro" not in text
    assert "Proponer resumen" not in text
    assert "Carta de presentación" not in text
    assert 'id="attempt-open"' not in raw
    assert "<dialog" not in raw


# --- C.5: what a real browser showed ------------------------------------------------

CSS = (Path(__file__).resolve().parents[2] / "src" / "web" / "static" / "app.css").read_text(
    encoding="utf-8"
)


def _script(client, application_id) -> str:
    raw = client.get(f"/applications/{application_id}").text
    return raw[raw.index("(function () {") : raw.index("</script>", raw.index("startPoll"))]


def test_the_dialog_is_centred_and_a_full_screen_sheet_on_a_phone():
    """Preflight zeroes the UA's `margin: auto`, and `dialog:modal` caps the width."""
    desktop = re.search(r"\.attempt-modal\{[^}]*\}", CSS).group(0)
    assert "margin:auto" in desktop

    phone = re.search(r"@media \(max-width:640px\)\{\.attempt-modal\{[^}]*\}", CSS).group(0)
    assert "max-width:none" in phone
    assert "max-height:none" in phone
    assert "inset:0" in phone


def test_the_script_blocks_a_second_paid_attempt_while_one_is_in_flight(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    raw = client.get(f"/applications/{application.id}").text
    script = _script(client, application.id)

    assert 'id="attempt-submit"' in raw
    assert "Analizando tu documento… puede tardar hasta un minuto." in raw
    assert "submit.disabled = busy" in script
    assert "file.disabled = busy" in script
    # The body is read before the file input is disabled: a disabled input is not sent.
    assert script.index("new FormData(form)") < script.index("setBusy(true)")
    assert ".catch(" in script, "a network failure shows the error line"
    assert script.index(".catch(") < script.index("setBusy(false)")


def test_the_file_input_is_the_drop_zone_and_keeps_its_id(client, session, career, provider):
    """§12.4 replaced the "Elegir archivo" button; the submit script still finds the input."""
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    raw = client.get(f"/applications/{application.id}").text

    assert 'id="attempt-file"' in raw and 'name="file"' in raw
    assert 'for="attempt-file"' in raw and "data-dropzone" in raw
    assert "Arrastra tu CV aquí o elige un archivo" in raw
    assert "Elegir archivo" not in raw


def test_the_cancel_button_asks_before_losing_an_unsaved_result(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    script = _script(client, application.id)

    assert 'getElementById("attempt-close").addEventListener("click", requestClose)' in script
    body = script[script.index("function requestClose") :]
    assert "unsaved && !window.confirm" in body.split("modal.close")[0]


def test_opening_the_modal_polls_a_running_attempt(client, session, career, provider):
    application, _analysis, attempt = _run(client, session, career, provider)
    attempt.status = "running"
    attempt.finished_at = None
    session.commit()

    raw = client.get(f"/applications/{application.id}").text
    script = _script(client, application.id)

    assert 'data-status="running"' in raw, "the list row says it is running"
    assert f'data-attempt-url="/applications/{application.id}/attempts/{attempt.id}"' in raw
    opener = script[script.index('getElementById("attempt-open")') :].split("});")[0]
    assert "showModal" in opener
    assert "[data-status=\"running\"]" in opener
    assert "startPoll(running.dataset.attemptUrl)" in opener


def test_the_result_does_not_repeat_the_header_numbers(client, session, career, provider):
    application, _analysis, attempt = _run(client, session, career, provider)

    text = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    assert text.count("Techo con tu material") == 0
    assert "vs. análisis del puesto" in text, "the delta line stays"


def test_nothing_left_has_its_own_wording(client, session, career, provider):
    application, _analysis, attempt = _run(client, session, career, provider)
    attempt.report = {**attempt.report, "advice": []}
    session.commit()

    text = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    left = text[text.index("Qué queda") :]
    assert "Nada pendiente: ya usaste lo que tu material ofrece para esta oferta." in left
    assert "Nada nuevo" not in left
