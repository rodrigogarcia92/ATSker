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
from src.i18n import t
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

    assert "vs. análisis de la línea" in text
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
    # K6: the read-only report may carry the shared proposal dialog for its keywords button;
    # it never carries the F10 attempt modal.
    assert 'id="attempt-modal"' not in raw


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
    assert "vs. análisis de la línea" in text, "the delta line stays"


def test_nothing_left_has_its_own_wording(client, session, career, provider):
    application, _analysis, attempt = _run(client, session, career, provider)
    attempt.report = {**attempt.report, "advice": []}
    session.commit()

    text = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    left = text[text.index("Qué queda") :]
    assert "Nada pendiente: ya usaste lo que tu material ofrece para esta oferta." in left
    assert "Nada nuevo" not in left


# --- S5a: the level-1 state, the honest "Nuevo en este documento", the subheadings -------

# A requirement the file only mentions: the skills list names it, no bullet shows it (F5.5.2).
MENTIONED_GAP = {
    "requirement": "excel",
    "level": 1,
    "must_have": False,
    "bullet_id": None,
    "bullet_text": None,
    "blocking": False,
    "interpretation": "",
}


def test_a_mentioned_skill_is_listed_in_whats_left_with_its_ochre_chip(
    client, session, career, provider
):
    """§12.1 item 3, amended 2026-10-13: the pop-up's *Qué queda* says where the term is
    and what would make it count, and the chip beside it is the ochre mentioned state."""
    application, _analysis, attempt = _run(client, session, career, provider)
    attempt.report = {
        **attempt.report,
        "gaps": {**(attempt.report.get("gaps") or {}), "gaps": [MENTIONED_GAP]},
    }
    session.commit()

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    left = raw[raw.index("Qué queda") :]

    assert 'class="chip chip-mentioned"' in left, "level 1 is mentioned, never a missing ✕"
    assert "✕</span> excel" not in left
    assert (
        "«excel» solo aparece en tu lista de habilidades o en el resumen: escríbelo en un "
        "bullet que muestre cómo lo usaste para que cuente como evidencia."
    ) in plain(left)


def test_the_result_shows_no_claims_line_and_no_above_ceiling_line(
    client, session, career, provider
):
    """Both flags are still computed and stored (F10.5), and neither is shown: a new CV is
    expected to carry new information and the user decides whether it is true."""
    application, _analysis, attempt = _run(client, session, career, provider)
    attempt.report = {
        **attempt.report,
        "flags": {
            **attempt.report["flags"],
            "claims": ["37%"],
            "above_ceiling": True,
            "new_terms": ["tablas dinámicas"],
            "titles": ["Directora de datos"],
        },
    }
    session.commit()

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text
    text = plain(raw)

    assert "37%" not in text
    assert "Cifras, fechas o nombres" not in text
    assert "puntúa por encima de lo que tu material permite" not in text
    assert attempt.report["flags"]["claims"] == ["37%"], "the stored report keeps both"
    assert attempt.report["flags"]["above_ceiling"] is True
    assert "Habilidades y palabras clave nuevas:" in text
    assert "tablas dinámicas" in text and "Directora de datos" in text
    assert "Revisa que sea cierto" in text
    assert (
        f'href="/applications/{application.id}/attempts/{attempt.id}/incorporate"' in raw
    ), "the line links to the page that adds it to the material"


def test_an_older_stored_attempt_still_names_what_its_flags_carried(
    client, session, career, provider
):
    """A row stored before §12.9's key existed falls back to the skill flags it has and
    never reads "nothing new" — the operator's earlier attempts are exactly this case."""
    application, _analysis, attempt = _run(client, session, career, provider)
    flags = {
        key: value for key, value in attempt.report["flags"].items() if key != "new_terms"
    }
    flags["skills"] = ["tablas dinámicas"]
    attempt.report = {**attempt.report, "flags": flags}
    session.commit()

    text = plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)

    assert "tablas dinámicas" in text
    assert "Nada nuevo frente a tu material." not in text


def test_the_popup_subheadings_are_the_one_bold_class(client, session, career, provider):
    """§2, amended 2026-10-13: 600 is loaded for these three and nothing else in the app."""
    application, _analysis, attempt = _run(client, session, career, provider)

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}").text

    for key in ("attempt.change.title", "attempt.flags.title", "attempt.left.title"):
        assert f'<h3 class="pt-1 dialog-subhead">{t(key, "es")}</h3>' in raw
    assert raw.count("dialog-subhead") == 3, "only the pop-up's own subheadings"
    # The weight itself is loaded by the document head, which a partial does not carry.
    assert "family=Hanken+Grotesk:wght@400;600" in client.get(
        f"/applications/{application.id}"
    ).text, "the weight has to be loaded"


def test_the_dialog_subhead_and_the_mentioned_chip_are_the_styles_the_screens_say():
    rule = re.search(r"\.dialog-subhead\{[^}]*\}", CSS).group(0)
    assert "font-size:1.125rem" in rule and "font-weight:600" in rule
    assert "font-synthesis-weight:none" in CSS, "600 is loaded, never synthesised"

    chip = re.search(r"\.chip-mentioned\{[^}]*\}", CSS).group(0)
    assert "1px" in chip and "var(--ochre)" in chip and "dashed" not in chip
