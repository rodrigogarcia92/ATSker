"""Attempt actions (PRD F10.7, C.3): sent, the merge hand-off and the destination.

The merge writes only what the attempt made new, only when it is confirmed, and never
touches a track unless the user chose a destination. One attempt at a time can be the
sent one.
"""

import uuid
from decimal import Decimal

import pytest

from src.applications import create_application
from src.attempt_merge import apply_attempt_merge, apply_destination, attempt_draft, merge_plan
from src.bullets import list_bullets
from src.extract import client as extract_client
from src.models import Application, ApplicationAttempt
from src.tracks import track_bullets
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    grading_payload,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes, plain


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> AttemptProvider:
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


FETCH = {"X-Requested-With": "fetch"}
INVENTED = "Entrené un modelo de machine learning en producción"


def _attempt_with_new_bullet(
    client, session, career, provider
) -> tuple[Application, ApplicationAttempt]:
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    provider.answers["ResumeExtraction"] = resume_payload(INVENTED)
    provider.answers["EvidenceGrading"] = grading_payload(None)
    client.post(
        f"/applications/{application.id}/attempts",
        files={"file": ("cv.docx", docx_bytes("Experiencia", INVENTED), DOCX_TYPE)},
        follow_redirects=False,
    )
    return application, session.query(ApplicationAttempt).one()

NEW_TEXT = "Entrené un modelo de machine learning en producción"
MASTER_TEXT = "Reduje 30% el tiempo de reporte con Python"


def _report() -> dict:
    return {
        "draft": {
            "language": "es",
            "headline": "Analista",
            "summary": "",
            "skills": ["machine learning"],
            "roles": [
                {
                    "employer": "Acme",
                    "title": "Analista",
                    "start_date": None,
                    "end_date": None,
                    "bullets": [
                        {"text": MASTER_TEXT, "chips": ["python"]},
                        {"text": NEW_TEXT, "chips": []},
                    ],
                }
            ],
            "educations": [],
            "certifications": [],
        },
        "bullets": [
            {"id": "master", "temporary": False, "role_id": "r", "text": MASTER_TEXT},
            {"id": "temp", "temporary": True, "role_id": "r", "text": NEW_TEXT},
        ],
        "flags": {
            "skills": ["machine learning"],
            "claims": [],
            "titles": [],
            "above_ceiling": False,
        },
    }


def test_only_new_or_changed_material_travels_to_the_review():
    draft = attempt_draft(_report())

    texts = [bullet.text for role in draft.roles for bullet in role.bullets]
    assert texts == [NEW_TEXT], "a matched bullet is already master data"
    assert draft.skills == ["machine learning"]
    assert draft.educations == [] and draft.certifications == []


def test_the_merge_writes_only_when_it_is_applied_and_never_touches_a_track(session, career):
    draft = attempt_draft(_report())
    plan = merge_plan(career.first_profile.id, session, draft)
    selection_before = [bullet.id for bullet in track_bullets(
        career.first_profile.id, session, career.first_track.id
    )]

    result = apply_attempt_merge(career.first_profile.id, session, draft=draft, plan=plan)
    session.commit()

    assert result["counts"]["bullets_created"] == 1
    assert len(result["bullet_ids"]) == 1
    assert result["counts"]["skills_added"] == 1
    selection_after = [bullet.id for bullet in track_bullets(
        career.first_profile.id, session, career.first_track.id
    )]
    assert selection_after == selection_before, "the merge alone never touches a track"


def test_the_destination_is_a_separate_choice(session, career):
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:dest",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
        track_id=career.first_track.id,
    )
    session.commit()
    draft = attempt_draft(_report())
    plan = merge_plan(career.first_profile.id, session, draft)
    merged = apply_attempt_merge(career.first_profile.id, session, draft=draft, plan=plan)
    before = [bullet.id for bullet in track_bullets(
        career.first_profile.id, session, career.first_track.id
    )]

    # `solo mi material` (the default) writes nothing to any track.
    assert apply_destination(
        career.first_profile.id,
        session,
        application=application,
        bullet_ids=merged["bullet_ids"],
        choice="solo",
    ) is None
    assert [
        bullet.id
        for bullet in track_bullets(career.first_profile.id, session, career.first_track.id)
    ] == before

    # `este puesto` appends, never replaces.
    chosen = apply_destination(
        career.first_profile.id,
        session,
        application=application,
        bullet_ids=merged["bullet_ids"],
        choice="este",
    )
    session.commit()
    assert chosen == career.first_track.id
    ids = [bullet.id for bullet in track_bullets(
        career.first_profile.id, session, career.first_track.id
    )]
    appended = [value for value in ids if value not in before]
    assert [str(value) for value in merged["bullet_ids"]] == [str(value) for value in appended]


def test_the_review_page_writes_nothing_until_it_is_confirmed(client, session, career, provider):
    application, attempt = _attempt_with_new_bullet(client, session, career, provider)
    before_bullets = len(list_bullets(career.first_profile.id, session, active_only=False))
    before_track = [
        bullet.id
        for bullet in track_bullets(career.first_profile.id, session, career.first_track.id)
    ]

    page = plain(
        client.get(f"/applications/{application.id}/attempts/{attempt.id}/incorporate").text
    )

    assert "Incorporar a mi material" in page
    assert INVENTED in page, "the review shows what would be written"
    assert len(list_bullets(career.first_profile.id, session, active_only=False)) == before_bullets

    response = client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/incorporate",
        data={"destination": "solo"},
    )

    assert response.status_code == 200
    after = len(list_bullets(career.first_profile.id, session, active_only=False))
    assert after == before_bullets + 1
    assert [
        bullet.id
        for bullet in track_bullets(career.first_profile.id, session, career.first_track.id)
    ] == before_track, "the default destination touches no track"


def test_choosing_this_track_appends_the_new_bullet(client, session, career, provider):
    application, attempt = _attempt_with_new_bullet(client, session, career, provider)
    before_track = [
        bullet.id
        for bullet in track_bullets(career.first_profile.id, session, career.first_track.id)
    ]

    client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/incorporate",
        data={"destination": "este"},
    )

    after_track = [
        bullet.id
        for bullet in track_bullets(career.first_profile.id, session, career.first_track.id)
    ]
    assert len(after_track) == len(before_track) + 1
    assert after_track[: len(before_track)] == before_track, "append, never replace"


def test_only_one_attempt_can_be_the_sent_one(client, session, career):
    login(client, career.first.email)
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )
    first = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_sha256="a" * 64,
        prompt_versions={},
    )
    second = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=2,
        status="done",
        file_sha256="b" * 64,
        prompt_versions={},
    )
    session.add_all([first, second])
    session.commit()

    assert client.post(
        f"/applications/{application.id}/attempts/{first.id}/sent", headers=FETCH
    ).status_code == 200
    session.expire_all()
    assert first.is_sent is True
    assert session.get(Application, application.id).sent_attempt_id == first.id

    assert client.post(
        f"/applications/{application.id}/attempts/{second.id}/sent", headers=FETCH
    ).status_code == 200
    session.expire_all()
    sent = [row for row in (first, second) if row.is_sent]
    assert len(sent) == 1 and sent[0].id == second.id
    assert session.get(Application, application.id).sent_attempt_id == second.id


# --- D1: the modal's actions stay in the modal (F10.1, F10.7) ---


def _done_attempt(session, career, application) -> ApplicationAttempt:
    attempt = ApplicationAttempt(
        application_id=application.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_sha256="c" * 64,
        prompt_versions={},
        report={"draft": {"language": "es"}, "flags": {}},
    )
    session.add(attempt)
    session.commit()
    return attempt


def _plain_application(session, career):
    return create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )


def test_discard_without_the_header_redirects_back_to_the_modal(client, session, career):
    login(client, career.first.email)
    application = _plain_application(session, career)
    attempt = _done_attempt(session, career, application)

    response = client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/discard",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/applications/{application.id}?attempt={attempt.id}"
    session.expire_all()
    assert attempt.report["draft"] is None, "the draft is blanked"
    assert attempt.report["flags"] == {}, "and the report is kept"


def test_discard_with_the_fetch_header_returns_the_partial(client, session, career):
    login(client, career.first.email)
    application = _plain_application(session, career)
    attempt = _done_attempt(session, career, application)

    response = client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/discard",
        headers=FETCH,
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "data-attempt" in response.text and "<html" not in response.text
    session.expire_all()
    assert attempt.report["draft"] is None


@pytest.mark.parametrize("headers", [{}, FETCH], ids=["no-js", "fetch"])
def test_sent_sets_the_flag_either_way(client, session, career, headers):
    login(client, career.first.email)
    application = _plain_application(session, career)
    attempt = _done_attempt(session, career, application)

    response = client.post(
        f"/applications/{application.id}/attempts/{attempt.id}/sent",
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code == (200 if headers else 303)
    if headers:
        assert "data-attempt" in response.text and "<html" not in response.text
    else:
        assert response.headers["location"] == (
            f"/applications/{application.id}?attempt={attempt.id}"
        )
    session.expire_all()
    assert attempt.is_sent is True


def test_the_report_opens_the_modal_only_for_an_attempt_of_this_application(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    attempt = _done_attempt(session, career, application)
    other = _plain_application(session, career)
    foreign = ApplicationAttempt(
        application_id=other.id,
        profile_id=career.first_profile.id,
        attempt_no=1,
        status="done",
        file_sha256="d" * 64,
        prompt_versions={},
    )
    theirs_application = create_application(
        career.second_profile.id,
        session,
        jd_text="Otra oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Otro",
    )
    theirs = ApplicationAttempt(
        application_id=theirs_application.id,
        profile_id=career.second_profile.id,
        attempt_no=1,
        status="done",
        file_sha256="e" * 64,
        prompt_versions={},
    )
    session.add_all([foreign, theirs])
    session.commit()

    opened = client.get(f"/applications/{application.id}?attempt={attempt.id}")
    assert opened.status_code == 200
    assert f'data-open-attempt="{attempt.id}"' in opened.text

    for other_id in (theirs.id, foreign.id, uuid.uuid4()):
        page = client.get(f"/applications/{application.id}?attempt={other_id}")
        assert page.status_code == 200
        assert "data-open-attempt" not in page.text


def test_the_script_delegates_submit_for_sent_and_discard_and_checks_ok(
    client, session, career, provider
):
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    page = client.get(f"/applications/{application.id}").text

    script = page[page.index("F10.7: \"Marcar como enviada\""):]
    script = script[: script.index('document.getElementById("attempt-close")')]
    assert 'status.addEventListener("submit"' in script
    assert "(sent|discard)" in script
    assert '"X-Requested-With": "fetch"' in script
    assert script.index("response.ok") < script.index("status.innerHTML = html")
    assert "unsaved = true" not in script
