"""The attempt modal and the result's content order (PRD F10.1, F10.4, C.1).

The analysis page carries a native `<dialog>` with the upload and the list; a finished
attempt's partial renders F10.4's order (Job Match against the ceiling, the delta vs
the analysis with the stability band, the sub-scores with their ceilings, what changed,
what is new, what is left, the cost and the full-report link); a `running` partial
carries the URL the modal polls; and the attempt's own full report is read-only.
"""

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
