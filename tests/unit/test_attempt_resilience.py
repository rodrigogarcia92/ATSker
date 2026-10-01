"""C.0: a run never lingers, never counts stale, and never blocks the server.

Three failure modes a 30-90 s run can have, each asserted here: a pipeline exception
must land on the row as `failed`; a `running` row past the staleness window must not
count towards the limit; and the synchronous run must not freeze the event loop, so a
request to another page is served while it works.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from src.applications import create_application
from src.attempts import MAX_ATTEMPTS, counted_attempts
from src.extract import client as extract_client
from src.extract.client import ProviderUnavailable
from src.models import ApplicationAttempt
from src.web.routes import attempts as attempt_routes
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


def test_a_grading_failure_fails_the_attempt_without_a_500(
    client, session, career, provider, monkeypatch
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    def unavailable(*_args, **_kwargs):
        raise ProviderUnavailable("the provider is down")

    monkeypatch.setattr(attempt_routes, "run_pipeline", unavailable)

    response = upload(client, application.id, docx_bytes("Experiencia", "Reduje el cierre"))

    assert response.status_code == 200
    attempt = session.query(ApplicationAttempt).one()
    assert attempt.status == "failed"
    assert attempt.error, "the row carries the reason"
    assert counted_attempts(career.first_profile.id, session, application.id) == 0


def test_an_unexpected_failure_is_logged_and_fails_the_attempt(
    client, session, career, provider, monkeypatch, caplog
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)

    def broken(*_args, **_kwargs):
        raise ValueError("something no one expected")

    monkeypatch.setattr(attempt_routes, "run_pipeline", broken)

    with caplog.at_level("ERROR"):
        response = upload(client, application.id, docx_bytes("Experiencia", "Reduje el cierre"))

    assert response.status_code == 200
    assert session.query(ApplicationAttempt).one().status == "failed"
    assert "something no one expected" in caplog.text


def test_a_stale_running_row_does_not_count_towards_the_limit(session, career):
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:stale",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )
    stale = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="running",
        file_sha256="a" * 64,
        prompt_versions={},
        created_at=datetime.now(UTC) - timedelta(minutes=11),
    )
    fresh = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=2,
        status="running",
        file_sha256="b" * 64,
        prompt_versions={},
        created_at=datetime.now(UTC),
    )
    session.add_all([stale, fresh])
    session.commit()

    assert counted_attempts(career.first_profile.id, session, application.id) == 1
    assert MAX_ATTEMPTS == 10


def test_a_slow_run_does_not_block_other_requests(client, session, career, provider, monkeypatch):
    """The handler is synchronous, so Starlette runs it off the event loop."""
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    release = threading.Event()

    def slow(*_args, **_kwargs):
        release.wait(timeout=5)
        raise ProviderUnavailable("done")

    monkeypatch.setattr(attempt_routes, "run_pipeline", slow)

    result: dict[str, object] = {}

    def run_upload():
        result["response"] = upload(
            client, application.id, docx_bytes("Experiencia", "Reduje el cierre")
        )

    worker = threading.Thread(target=run_upload)
    worker.start()
    time.sleep(0.2)
    started = time.perf_counter()
    health = client.get("/health")
    elapsed = time.perf_counter() - started
    release.set()
    worker.join(timeout=10)

    assert health.status_code == 200
    assert elapsed < 0.5, "another request was served while the run was in flight"
    assert result["response"].status_code == 200
    assert "Fallido" in plain(result["response"].text)
