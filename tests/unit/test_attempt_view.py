"""What the attempt result says it compares, and what counts as a change (PRD F10.4, D2).

Two deltas, each labelled with its reference: the previous finished attempt and the
posting analysis. A change in any score is a change, even when searches, gaps and
readability are all as they were.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from src.applications import create_application
from src.attempt_flags import change_list
from src.attempts import attempt_view, previous_done_attempt
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.test_ingest_routes import plain


def _score(capped: int, **sub: float) -> dict:
    return {
        "score": {
            "capped": capped,
            "sub_scores": {name: {"value": value} for name, value in sub.items()},
        }
    }


def _row(session, profile_id, application, number, *, status="done", job_match=None, report=None):
    row = ApplicationAttempt(
        application_id=application.id,
        profile_id=profile_id,
        attempt_no=number,
        file_sha256=f"{number:064d}",
        file_format="docx",
        status=status,
        job_match=job_match,
        report=report if report is not None else _score(job_match or 0),
        prompt_versions={},
        created_at=datetime.now(UTC),
    )
    session.add(row)
    session.flush()
    return row


def _application(session, career, capped: int = 69):
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report=_score(capped),
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )
    session.commit()
    return application


def _status(client, application, attempt) -> str:
    return plain(client.get(f"/applications/{application.id}/attempts/{attempt.id}").text)


def test_each_delta_says_what_it_compares(client, session, career):
    login(client, career.first.email)
    application = _application(session, career, capped=69)
    profile = career.first_profile.id
    first = _row(session, profile, application, 1, job_match=63)
    second = _row(session, profile, application, 2, job_match=59)
    session.commit()

    later = _status(client, application, second)
    assert "-4 vs. intento 1" in later
    assert "-10 vs. análisis del puesto" in later

    earlier = _status(client, application, first)
    assert "vs. análisis del puesto" in earlier
    assert "vs. intento" not in earlier, "the first attempt has no previous one"


def test_a_failed_attempt_is_not_the_previous_one(session, career):
    profile = career.first_profile.id
    application = _application(session, career)
    first = _row(session, profile, application, 1, job_match=63)
    failed = _row(session, profile, application, 2, status="failed")
    third = _row(session, profile, application, 3, job_match=59)

    rows = [first, failed, third]
    assert previous_done_attempt(rows, third) is first
    view = attempt_view(third, analysis_score=69, previous=previous_done_attempt(rows, third))
    assert view["previous_no"] == 1
    assert view["delta_previous"] == -4 and view["delta_analysis"] == -10


def test_a_previous_attempt_without_a_score_gives_no_previous_delta(session, career):
    profile = career.first_profile.id
    application = _application(session, career)
    first = _row(session, profile, application, 1, job_match=None, report={})
    second = _row(session, profile, application, 2, job_match=59)

    view = attempt_view(second, analysis_score=69, previous=first)

    assert view["delta_previous"] is None and view["delta_analysis"] == -10


def test_a_small_delta_reads_as_no_significant_change(session, career):
    profile = career.first_profile.id
    application = _application(session, career)
    first = _row(session, profile, application, 1, job_match=63)
    second = _row(session, profile, application, 2, job_match=63)

    view = attempt_view(second, analysis_score=63, previous=first)

    assert view["delta_previous_significant"] is False
    assert view["delta_analysis_significant"] is False


def test_a_score_change_is_listed_and_is_not_no_change(client, session, career):
    login(client, career.first.email)
    application = _application(session, career)
    profile = career.first_profile.id
    before = _score(63, experience=0.91, skills=0.5)
    after = _score(59, experience=0.42, skills=0.5)
    change = change_list(before, after)
    _row(session, profile, application, 1, job_match=63, report=before)
    second = _row(
        session, profile, application, 2, job_match=59, report={**after, "change": change}
    )
    session.commit()

    assert change["sub_scores"] == [{"name": "experience", "before": 91, "after": 42}]
    assert change["score"] == {"before": 63, "after": 59}
    page = _status(client, application, second)
    assert "Experiencia 91 → 42" in page
    assert "Encaje total 63 → 59" in page
    assert page.index("Encaje total 63") < page.index("Experiencia 91")
    assert "Sin cambios respecto al intento anterior" not in page


def test_everything_equal_still_reads_as_no_change(client, session, career):
    login(client, career.first.email)
    application = _application(session, career)
    profile = career.first_profile.id
    same = _score(63, experience=0.91)
    change = change_list(same, same)
    _row(session, profile, application, 1, job_match=63, report=same)
    second = _row(
        session, profile, application, 2, job_match=63, report={**same, "change": change}
    )
    session.commit()

    assert change["score"] is None and change["sub_scores"] == []
    assert "Sin cambios respecto al intento anterior" in _status(client, application, second)
