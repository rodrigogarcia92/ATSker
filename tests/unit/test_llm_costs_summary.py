"""`scripts/llm_costs.py summary`: the trial's meter, read-only (queue M5, PRD §7)."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import scripts.llm_costs as llm_costs
from src.models import LlmCall


@pytest.fixture
def ledger(monkeypatch, session):
    """The script reads the test session, never a developer's DATABASE_URL."""

    @contextmanager
    def scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(llm_costs, "session_scope", scope)
    return session


def row(model, purpose, prompt, completion, cost, *, days_ago=0, degenerate=False):
    return LlmCall(
        purpose=purpose,
        prompt_version="v1",
        model=model,
        input_hash="h" * 64,
        response_json={"secret": "personal data that must never be printed"},
        prompt_tokens=prompt,
        completion_tokens=completion,
        cost_usd=Decimal(cost),
        degenerate=degenerate,
        created_at=datetime.now(UTC) - timedelta(days=days_ago, hours=1),
    )


@pytest.fixture
def filled(ledger):
    ledger.add_all(
        [
            row("model/a", "generate_summary", 1000, 100, "0.010000"),
            row("model/a", "generate_summary", 2000, 300, "0.030000", degenerate=True),
            row("model/a", "grade", 500, 50, "0.002000"),
            row("model/b", "generate_summary", 800, 90, "0.004000"),
            row("model/b", "grade", 400, 40, "0.001000"),
            row("model/b", "grade", 100, 10, "0.000500", days_ago=30),
        ]
    )
    ledger.commit()
    return ledger


def lines_of(capsys) -> list[list[str]]:
    return [line.split() for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_groups_by_model_and_purpose_with_sums_and_the_degenerate_count(filled, capsys):
    assert llm_costs.cmd_summary("7d") == 0

    out = lines_of(capsys)
    by_group = {(r[0], r[1]): r[2:] for r in out if r[0].startswith("model/") and len(r) > 6}
    # calls, purged, prompt tok, compl tok, cost, avg/call
    assert by_group[("model/a", "generate_summary")] == [
        "2", "1", "3000", "400", "$0.040000", "$0.020000",
    ]  # fmt: skip
    assert by_group[("model/a", "grade")] == ["1", "0", "500", "50", "$0.002000", "$0.002000"]
    assert by_group[("model/b", "generate_summary")][0] == "1"
    assert by_group[("model/b", "grade")][0] == "1", "the 30-day-old row is outside the window"


def test_prints_a_total_per_model(filled, capsys):
    llm_costs.cmd_summary("7d")

    totals = {r[0]: r for r in lines_of(capsys) if "(all" in " ".join(r)}
    assert totals["model/a"][3:] == ["3", "1", "3500", "450", "$0.042000", "$0.014000"]
    assert totals["model/b"][3:] == ["2", "0", "1200", "130", "$0.005000", "$0.002500"]


def test_by_purpose_totals_per_purpose(filled, capsys):
    llm_costs.cmd_summary("7d", "purpose")

    totals = [r for r in lines_of(capsys) if r[:3] == ["(all", "models)", "generate_summary"]]
    assert totals and totals[0][3:6] == ["3", "1", "3800"]


def test_never_prints_the_stored_answer_or_a_hash(filled, capsys):
    llm_costs.cmd_summary("7d")

    printed = capsys.readouterr().out
    assert "personal data" not in printed and "h" * 8 not in printed


def test_an_empty_window_says_so(ledger, capsys):
    assert llm_costs.cmd_summary("2d") == 0

    assert "no model calls in that window" in capsys.readouterr().out


@pytest.mark.parametrize("window", ["2d", "48h", "2026-01-01"])
def test_since_accepts_days_hours_and_a_date(filled, capsys, window):
    assert llm_costs.main(["summary", "--since", window]) == 0

    assert "model/a" in capsys.readouterr().out


def test_the_date_form_reaches_the_old_row(filled, capsys):
    days_ago = (datetime.now(UTC) - datetime(2026, 1, 1, tzinfo=UTC)).days
    assert days_ago > 30

    llm_costs.main(["summary", "--since", "2026-01-01"])

    by_group = {(r[0], r[1]): r[2] for r in lines_of(capsys) if len(r) > 6}
    assert by_group[("model/b", "grade")] == "2"


def test_the_help_says_cost_per_analysis_is_not_printed(capsys):
    with pytest.raises(SystemExit):
        llm_costs.main(["summary", "--help"])

    assert "cost per analysis is not printed" in " ".join(capsys.readouterr().out.split())


def test_purge_and_the_list_still_parse(filled, capsys):
    assert llm_costs.main(["purge", "--hash", "0" * 64]) == 1
    assert "no call matches" in capsys.readouterr().out
    assert llm_costs.main(["--since", "7d"]) == 0
    assert "total:" in capsys.readouterr().out
