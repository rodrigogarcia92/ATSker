"""Application attempts: ownership, deletion and the ledger (PRD F10, F10.8, F2.8).

These cover what migration 0014 and the F2.8 wiring add before any route exists: a
row carries its `profile_id`, so another profile's attempt is simply not found
(`src.scoping`); deleting an application takes its attempts with it; and "Eliminar
todo" counts attempts and blanks the personal answers the attempt calls leave in the
ledger.
"""

import uuid
from decimal import Decimal

from sqlalchemy import select

from src.applications import create_application
from src.deletion import (
    ATTEMPT_EXTRACT,
    ATTEMPT_GRADE,
    delete_application,
    delete_everything,
    impact_application,
    impact_everything,
)
from src.models import Application, ApplicationAttempt, LlmCall
from src.scoping import owned_row


def _application(profile_id, session):
    return create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )


def _attempt(profile_id, session, application_id, *, attempt_no: int = 1) -> ApplicationAttempt:
    row = ApplicationAttempt(
        application_id=application_id,
        profile_id=profile_id,
        attempt_no=attempt_no,
        file_sha256="a" * 64,
        file_format="docx",
        lang="es",
        report={"attempt": attempt_no},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    session.add(row)
    session.flush()
    return row


def _ledger(session, profile_id, purpose: str) -> LlmCall:
    row = LlmCall(
        purpose=purpose,
        prompt_version="v1",
        model="test/model-v1",
        input_hash=uuid.uuid4().hex,
        response_json={"answer": "personal content"},
        prompt_tokens=7,
        completion_tokens=3,
        cost_usd=Decimal("0.001000"),
        profile_id=profile_id,
    )
    session.add(row)
    return row


def test_an_attempt_is_owned_by_its_profile(session, career):
    """F1's isolation: the same lookup returns the row for its owner and None for the
    other profile, which is what the routes turn into a 404."""
    application = _application(career.first_profile.id, session)
    attempt = _attempt(career.first_profile.id, session, application.id)
    session.commit()

    assert owned_row(ApplicationAttempt, session, career.first_profile.id, attempt.id) is attempt
    assert owned_row(ApplicationAttempt, session, career.second_profile.id, attempt.id) is None
    assert owned_row(ApplicationAttempt, session, career.first_profile.id, uuid.uuid4()) is None
    assert owned_row(ApplicationAttempt, session, career.first_profile.id, "not-a-uuid") is None


def test_deleting_an_application_deletes_its_attempts_and_reports_the_count(session, career):
    """F2.8: the numbers the confirmation screen shows are the rows that go."""
    application = _application(career.first_profile.id, session)
    first = _attempt(career.first_profile.id, session, application.id, attempt_no=1)
    second = _attempt(career.first_profile.id, session, application.id, attempt_no=2)
    session.commit()

    assert impact_application(career.first_profile.id, session, application.id) == {
        "applications": 1,
        "application_attempts": 2,
    }

    assert delete_application(career.first_profile.id, session, application.id) == {
        "applications": 1,
        "application_attempts": 2,
    }
    session.commit()

    assert session.get(Application, application.id) is None
    assert session.get(ApplicationAttempt, first.id) is None
    assert session.get(ApplicationAttempt, second.id) is None


def test_eliminar_todo_counts_attempts_and_redacts_their_ledger(session, career):
    """F2.8 + A9: attempts are part of the profile's data, and the attempt calls are
    personal — their answers are blanked, their tokens and cost kept."""
    application = _application(career.first_profile.id, session)
    attempt = _attempt(career.first_profile.id, session, application.id)
    extract_row = _ledger(session, career.first_profile.id, ATTEMPT_EXTRACT)
    grade_row = _ledger(session, career.first_profile.id, ATTEMPT_GRADE)
    session.commit()

    counts = impact_everything(career.first_profile.id, session)
    assert counts["application_attempts"] == 1
    assert counts["ledger_redacted"] == 2

    totals = delete_everything(career.first_profile.id, session)
    session.commit()

    assert totals["application_attempts"] == 1
    assert session.get(ApplicationAttempt, attempt.id) is None
    for row in (extract_row, grade_row):
        fresh = session.get(LlmCall, row.id)
        assert fresh.response_json == {} and fresh.degenerate is True
        assert fresh.prompt_tokens == 7 and fresh.cost_usd == Decimal("0.001000")
    assert session.scalars(select(Application)).all() == []
