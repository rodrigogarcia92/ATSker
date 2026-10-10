"""Role matching for an attempt (PRD F10.3 step 3, F5.5.2, D5).

A tailored CV retitles a role, but the job is the same one when the employer and the
start month are the same. A role that still matches nothing is scored from the file —
a transient `Role`, never stored — so its citations count in Experience like any other.
"""

import json
import re
import uuid
from datetime import date
from decimal import Decimal

import pytest

from src.applications import create_application
from src.attempt_merge import attempt_draft, merge_plan
from src.attempt_track import ephemeral_track, match_roles
from src.bullets import create_bullet
from src.extract import client as extract_client
from src.ingest.draft import DraftBullet, DraftRole, ResumeDraft
from src.models import ApplicationAttempt
from src.roles import create_role
from tests.conftest import login
from tests.unit.attempt_support import (
    AttemptProvider,
    analyzed_application,
    resume_payload,
)
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes

TEXTS = (
    "Diseñé tableros de seguimiento de indicadores para el ministerio",
    "Automaticé la consolidación mensual de reportes regionales",
    "Capacité a equipos regionales en el uso de los tableros",
)


def _application(profile_id, session, track_id):
    application = create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={"jd": {"language": "es"}},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
        track_id=track_id,
    )
    session.commit()
    return application


def _master(
    career,
    session,
    *,
    start=date(2020, 3, 1),
    title="Especialista en datos",
    employer="Empresa Demo 0",
):
    role = create_role(
        career.first_profile.id,
        session,
        employer=employer,
        title_es=title,
        title_en=None,
        start_date=start,
    )
    bullets = [
        create_bullet(
            career.first_profile.id,
            session,
            role_id=role.id,
            text_es=text,
            text_en=None,
            chips=[],
        )
        for text in TEXTS
    ]
    session.commit()
    return role, bullets


def _draft(
    *,
    title="Data Analyst & RBF Specialist",
    start: str | None = "2020-03",
    employer="Empresa Demo 0",
    texts=TEXTS,
):
    return ResumeDraft(
        language="es",
        headline="Analista de datos",
        roles=[
            DraftRole(
                employer=employer,
                title=title,
                start_date=start,
                bullets=[DraftBullet(text=text) for text in texts],
            )
        ],
    )


def _run(career, session, draft):
    application = _application(career.first_profile.id, session, career.first_track.id)
    return ephemeral_track(career.first_profile.id, session, application=application, draft=draft)


def test_a_retitled_role_with_the_same_employer_and_start_month_is_the_same_job(session, career):
    role, bullets = _master(career, session)

    result = _run(career, session, _draft())

    assert [snapshot.temporary for snapshot in result.snapshots] == [False] * 3
    assert [snapshot.id for snapshot in result.snapshots] == [str(b.id) for b in bullets]
    assert result.roles == (), "nothing is scored from the file"
    assert result.role_matching == (
        {
            "file_title": "Data Analyst & RBF Specialist",
            "matched_role_id": str(role.id),
            "by": "employer_start",
        },
    )


def test_a_role_with_the_same_title_is_matched_by_employer_and_title(session, career):
    role, _bullets = _master(career, session)

    result = _run(career, session, _draft(title="Especialista en datos"))

    assert [row["by"] for row in result.role_matching] == ["employer_title"]
    assert result.role_matching[0]["matched_role_id"] == str(role.id)
    assert result.roles == ()


def test_another_start_month_is_another_job_scored_from_the_file(session, career):
    _master(career, session)

    result = _run(career, session, _draft(start="2019-07"))

    assert [snapshot.temporary for snapshot in result.snapshots] == [True] * 3
    (transient,) = result.roles
    assert (transient.employer, transient.title) == (
        "Empresa Demo 0",
        "Data Analyst & RBF Specialist",
    )
    assert transient.start_date == date(2019, 7, 1) and transient.end_date is None
    assert {snapshot.role_id for snapshot in result.snapshots} == {str(transient.id)}
    assert transient not in session, "a transient role is never added to the session"
    assert result.role_matching[0]["by"] == "file_only"
    assert result.role_matching[0]["matched_role_id"] is None


def test_a_file_role_without_a_start_date_matches_nothing(session, career):
    _master(career, session)

    result = _run(career, session, _draft(start=None))

    assert [row["by"] for row in result.role_matching] == ["file_only"]
    assert result.roles[0].start_date is None


def test_two_master_roles_with_the_same_employer_and_month_are_ambiguous(session, career):
    _master(career, session)
    _master(career, session, title="Analista de monitoreo")

    result = _run(career, session, _draft())

    assert [row["by"] for row in result.role_matching] == ["file_only"]
    assert len(result.roles) == 1


def test_employers_that_differ_only_in_punctuation_are_one_employer(session, career):
    role, _bullets = _master(career, session, employer="Ministry of Education (Empresa Demo 0)")

    result = _run(career, session, _draft(employer="Ministry of Education Empresa Demo 0"))

    assert result.role_matching == (
        {
            "file_title": "Data Analyst & RBF Specialist",
            "matched_role_id": str(role.id),
            "by": "employer_start",
        },
    )
    assert result.roles == ()


# --- E3: the merge review matches roles the way scoring does ---

CHANGED = TEXTS[0] + " de educación"
BRAND_NEW = "Implementé un tablero de compras públicas para el ministerio"


def _plan_from_attempt(career, session, draft):
    """The merge plan "Incorporar a mi material" builds from an attempt on `draft`."""
    result = _run(career, session, draft)
    report = {
        "draft": draft.model_dump(mode="json"),
        "bullets": [snapshot.to_dict() for snapshot in result.snapshots],
        "flags": {"skills": []},
    }
    return merge_plan(career.first_profile.id, session, attempt_draft(report))


@pytest.mark.parametrize(
    ("master_title", "file_title"),
    [
        ("Especialista en datos", "Data Analyst & RBF Specialist"),
        ("Data Analyst & Results - Based Specialist", "Data Analyst & Results-Based Specialist"),
    ],
    ids=["retitled", "hyphen-only"],
)
def test_the_merge_plan_matches_a_retitled_role_to_the_master_role(
    session, career, master_title, file_title
):
    role, bullets = _master(career, session, title=master_title)

    plan = _plan_from_attempt(
        career,
        session,
        _draft(title=file_title, texts=(TEXTS[1], CHANGED, BRAND_NEW)),
    )

    (planned,) = plan.roles
    assert planned.existing_id == role.id, "the existing role, not a new one"
    assert planned.label != "new"
    assert [(b.label, b.existing_id) for b in planned.bullets] == [
        ("changed", bullets[0].id),
        ("new", None),
    ], "labelled against that role's own bullets"


def test_a_master_role_is_offered_to_one_file_role_only_in_the_merge_plan(session, career):
    role, _bullets = _master(career, session)
    draft = ResumeDraft(
        language="es",
        roles=[
            DraftRole(
                employer="Empresa Demo 0",
                title=title,
                start_date="2020-03",
                bullets=[DraftBullet(text=BRAND_NEW + suffix)],
            )
            for title, suffix in (("Analista A", ""), ("Analista B", " nuevo"))
        ],
    )

    matches, plan = match_roles(career.first_profile.id, session, draft)

    assert [m.by for m in matches] == ["employer_start", "file_only"]
    assert [r.existing_id for r in plan.roles] == [role.id, None]


def test_role_matching_carries_titles_only(session, career):
    _master(career, session)

    result = _run(career, session, _draft())

    assert set(result.role_matching[0]) == {"file_title", "matched_role_id", "by"}


class CitingProvider(AttemptProvider):
    """Grades the first bullet the prompt names at level 3 — the file's own, temporary one."""

    def __call__(self, payload: dict, api_key: str) -> dict:
        name = payload["response_format"]["json_schema"]["name"]
        if name == "EvidenceGrading":
            text = "\n".join(message["content"] for message in payload["messages"])
            found = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
            self.answers[name] = json.dumps(
                {
                    "grades": [
                        {
                            "index": 0,
                            "level": 3,
                            "basis": "direct",
                            "source": "bullet",
                            "evidence_id": found.group(0),
                            "transfer_reason": None,
                        },
                        {"index": 1, "level": 0, "basis": "none", "source": None},
                    ],
                    "task_grades": [],
                    "note": "una nota",
                }
            )
        return super().__call__(payload, api_key)


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> CitingProvider:
    stub = CitingProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def test_an_unmatched_role_counts_in_experience_from_the_file(client, session, career, provider):
    """The role's bullets are new, so they are graded; a level-3 citation of one of them
    used to add no years, because no role carried the temporary id (D5)."""
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, provider)
    data = json.loads(resume_payload(career.first_bullet.text_es))
    data["roles"][0].update(title="Analista Senior", start_date="2019-07")
    provider.answers["ResumeExtraction"] = json.dumps(data)

    client.post(
        f"/applications/{application.id}/attempts",
        files={
            "file": ("cv.docx", docx_bytes("Experiencia", career.first_bullet.text_es), DOCX_TYPE)
        },
        follow_redirects=False,
    )

    attempt = session.query(ApplicationAttempt).one()
    experience = attempt.report["score"]["sub_scores"]["experience"]
    assert experience["detail"]["relevant_years"] > 0
    assert [row["by"] for row in attempt.report["role_matching"]] == ["file_only"]
    assert attempt.report["role_matching"][0]["file_title"] == "Analista Senior"
