"""Readiness (PRD F10.6, C.2): one test per condition, plus the capped target.

The checklist is deterministic over the attempt's own report, so these build reports
by hand and flip one condition at a time.
"""

import uuid
from decimal import Decimal

from src.applications import create_application
from src.attempt_readiness import cap_target, readiness
from src.models import Application
from tests.conftest import login


def _report(*, capped=70, low=70, high=80, findings=(), queries=(), advice=(), alerts=()):
    return {
        "score": {"capped": capped},
        "ceiling": {
            "low": low,
            "high": high,
            "unreachable": {"requirements": [{"requirement": "MDM", "points": 6.0}]},
        },
        "gate": {"findings": list(findings)},
        "recall": {"queries": list(queries)},
        "advice": list(advice),
        "gaps": {"alerts": list(alerts)},
    }


def _passed(label="broad"):
    return {"label": label, "passed": True}


def test_the_baseline_is_ready_when_every_condition_holds():
    result = readiness(_report(queries=[_passed()]), target=None)

    assert result["ready"] is True
    assert [check["key"] for check in result["checks"]] == [
        "match",
        "readability",
        "search",
        "advice",
        "language",
    ]
    assert result["unreachable"] == [{"requirement": "MDM", "points": 6.0}]


def test_the_match_condition_fails_outside_the_band_and_passes_at_the_target():
    far = readiness(_report(capped=40, low=70, high=80, queries=[_passed()]), target=None)
    assert far["ready"] is False
    assert far["checks"][0]["ok"] is False

    aimed = readiness(_report(capped=40, low=70, high=80, queries=[_passed()]), target=40)
    assert aimed["checks"][0]["ok"] is True


def test_a_readability_blocker_blocks_readiness():
    report = _report(
        queries=[_passed()],
        findings=[{"check": "contact_in_margin", "severity": "blocker", "detail": {}}],
    )

    result = readiness(report, target=None)

    assert result["ready"] is False
    assert result["checks"][1] == {
        "key": "readability",
        "ok": False,
        "blockers": ["contact_in_margin"],
    }


def test_only_the_broad_and_core_searches_gate_readiness():
    strict_only = readiness(
        _report(queries=[_passed(), {"label": "strict", "passed": False}]), target=None
    )
    assert strict_only["checks"][2]["ok"] is True

    broad_fails = readiness(
        _report(queries=[{"label": "broad", "passed": False}]), target=None
    )
    assert broad_fails["checks"][2]["ok"] is False
    assert broad_fails["checks"][2]["failing"] == ["broad"]


def test_open_advice_of_kinds_one_to_four_blocks_readiness():
    result = readiness(
        _report(queries=[_passed()], advice=[{"kind": "surface_skill"}]), target=None
    )

    assert result["ready"] is False
    assert result["checks"][3]["ok"] is False
    assert result["checks"][3]["open"] == ["surface_skill"]


def test_a_language_mismatch_blocks_readiness():
    result = readiness(
        _report(queries=[_passed()], alerts=[{"kind": "language_mismatch"}]), target=None
    )

    assert result["ready"] is False
    assert result["checks"][4]["ok"] is False


def test_the_target_is_capped_at_the_ceiling_high():
    assert cap_target(95, 80) == 80
    assert cap_target(60, 80) == 60
    assert cap_target(None, 80) is None
    assert cap_target(90, None) == 90

    capped = readiness(_report(capped=80, low=80, high=80, queries=[_passed()]), target=95)
    assert capped["target"] == 80


def test_the_target_lives_on_the_application_and_is_capped(client, session, career):
    login(client, career.first.email)
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash=f"sha256:{uuid.uuid4().hex}",
        report={
            "score": {"capped": 70},
            "ceiling": {"low": 70, "high": 80, "unreachable": {"requirements": []}},
        },
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
        title="Puesto",
    )
    session.commit()

    response = client.post(
        f"/applications/{application.id}/target", data={"target": "95"}, follow_redirects=False
    )

    assert response.status_code == 303
    session.expire_all()
    assert session.get(Application, application.id).target_match == 80
