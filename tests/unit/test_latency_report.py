"""`scripts/latency_report.py`: response time read from the stored reports (PRD F12.4).

Synthetic reports on the test's SQLite: the percentiles are arithmetic, the cache
hits are excluded by the rule the script documents, and a report stored before the
timing existed is counted as skipped rather than guessed at.
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import scripts.latency_report as latency_report
from src.applications import create_application


@pytest.fixture
def reports(monkeypatch, session):
    """The script reads the test session, never a developer's DATABASE_URL."""

    @contextmanager
    def scope():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(latency_report, "session_scope", scope)
    return session


def call(purpose, latency_ms, *, cached=False, model="model/a"):
    return {"purpose": purpose, "latency_ms": latency_ms, "cached": cached, "model": model}


def store(session, profile_id, *, wall_ms=None, calls=(), days_ago=0, kind=None, steps_ms=None):
    """One stored report, with `created_at` where the window needs it."""
    report: dict = {"llm": {"calls": list(calls)}}
    if wall_ms is not None:
        report["llm"]["wall_ms"] = wall_ms
    if kind is not None:
        report["llm"]["kind"] = kind
    if steps_ms is not None:
        report["llm"]["steps_ms"] = dict(steps_ms)
    application = create_application(
        profile_id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:synthetic",
        report=report,
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    application.created_at = datetime.now(UTC) - timedelta(days=days_ago)
    session.commit()
    return application


@pytest.mark.parametrize(
    ("values", "p50", "p95"),
    [
        ([5], 5, 5),
        ([1, 2], 1, 2),
        (list(range(1, 11)), 5, 10),
        (list(range(1, 21)), 10, 19),
    ],
)
def test_nearest_rank_percentiles(values, p50, p95):
    """Rank ceil(f × n), 1-based, no interpolation: always a value that happened."""
    assert latency_report.percentile(values, 0.50) == p50
    assert latency_report.percentile(values, 0.95) == p95


def test_a_percentile_needs_a_value():
    with pytest.raises(ValueError):
        latency_report.percentile([], 0.50)


def test_wall_time_is_p50_p95_and_max_over_the_window(career, reports, capsys):
    for wall in (1000, 2000, 10000):
        store(reports, career.first_profile.id, wall_ms=wall, calls=[call("jd_extract", wall)])

    assert latency_report.cmd_report("7d", None) == 0

    out = capsys.readouterr().out
    assert "analyses: 3" in out
    assert "p50 2.0s" in out
    assert "p95 10.0s" in out
    assert "max 10.0s" in out


def test_cache_hits_are_excluded_from_the_latencies_and_counted(career, reports, capsys):
    store(
        reports,
        career.first_profile.id,
        wall_ms=4000,
        calls=[
            call("jd_extract", 1000),
            call("jd_extract", 3000),
            call("jd_extract", 0, cached=True),
            call("evidence_grade", 500),
        ],
    )

    latency_report.cmd_report("7d", None)

    rows = {
        words[0]: words[1:]
        for words in (line.split() for line in capsys.readouterr().out.splitlines())
        if words
    }
    assert rows["jd_extract"] == ["2", "1", "1.0s", "3.0s"], "n, cached, p50, p95"
    assert rows["evidence_grade"] == ["1", "0", "0.5s", "0.5s"]


def test_the_second_table_says_where_the_wall_time_went(career, reports, capsys):
    """R13.3: p50/p95 per step, over the reports in the window that recorded one."""
    for wall in (1000, 3000):
        store(
            reports,
            career.first_profile.id,
            wall_ms=wall,
            calls=[call("jd_extract", wall)],
            steps_ms={
                "reads": 100,
                "prepare_calls": wall - 400,
                "document": 100,
                "grading": 200,
                "scoring": 0,
                "notes": 0,
                "assemble": 0,
                "save": 20,
            },
        )
    # A report from before the steps: it counts in the wall table and has no row here.
    store(reports, career.first_profile.id, wall_ms=1000, calls=[call("jd_extract", 1000)])

    assert latency_report.cmd_report("7d", None) == 0

    rows = {
        line.split()[0]: line.split()[1:]
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    }
    assert rows["analyses:"][0] == "3"
    assert rows["reads"] == ["2", "0.1s", "0.1s"]
    assert rows["prepare_calls"] == ["2", "0.6s", "2.6s"], "one p50 per step, not per call"
    assert rows["save"] == ["2", "0.0s", "0.0s"], "the route's measured store is a step too"


def test_a_report_stored_before_the_timing_is_skipped_and_counted(career, reports, capsys):
    store(reports, career.first_profile.id, wall_ms=1000, calls=[call("jd_extract", 1000)])
    store(reports, career.first_profile.id, calls=[call("jd_extract", 1000)])

    latency_report.cmd_report("7d", None)

    out = capsys.readouterr().out
    assert "analyses: 1" in out
    assert "skipped (no timing): 1" in out


def test_the_window_leaves_out_older_analyses(career, reports, capsys):
    store(reports, career.first_profile.id, wall_ms=1000, calls=[call("jd_extract", 1000)])
    store(
        reports,
        career.first_profile.id,
        wall_ms=9000,
        calls=[call("jd_extract", 9000)],
        days_ago=30,
    )

    latency_report.cmd_report("7d", None)

    out = capsys.readouterr().out
    assert "analyses: 1" in out
    assert "max 1.0s" in out


def test_the_model_filter_keeps_only_that_models_calls(career, reports, capsys):
    store(
        reports,
        career.first_profile.id,
        wall_ms=1000,
        calls=[
            call("jd_extract", 1000, model="model/a"),
            call("gap_interpret", 2000, model="model/b"),
        ],
    )
    store(
        reports,
        career.first_profile.id,
        wall_ms=8000,
        calls=[call("jd_extract", 8000, model="model/a")],
    )

    latency_report.cmd_report("7d", "model/b")

    out = capsys.readouterr().out
    assert "analyses: 1" in out
    assert "max 1.0s" in out
    assert "gap_interpret" in out
    assert "jd_extract" not in out
    # The second report has no call of that model, so it is outside the filter.
    assert "skipped (no timing): 1" in out


def test_only_the_analyses_own_kind_is_read_by_default(career, reports, capsys):
    """F12.4: a recommendation's wall time starts at the shared preparation and an
    attempt's excludes the extraction it reused; neither belongs in an analysis p50.

    A report stored before kinds (every other test here) counts as the analysis it was.
    """
    store(
        reports,
        career.first_profile.id,
        wall_ms=1000,
        calls=[call("jd_extract", 1000)],
        kind="analysis",
    )
    store(
        reports,
        career.first_profile.id,
        wall_ms=9000,
        calls=[call("evidence_grade", 9000)],
        kind="recommendation",
    )
    store(
        reports,
        career.first_profile.id,
        wall_ms=5000,
        calls=[call("evidence_grade", 5000)],
        kind="attempt",
    )

    latency_report.cmd_report("7d", None)

    out = capsys.readouterr().out
    assert "analyses: 1" in out and "max 1.0s" in out
    assert "skipped (no timing): 0" in out, "another kind is out of scope, not skipped"


def test_all_reads_every_kind_and_attempt_reads_only_attempts(career, reports, capsys):
    store(reports, career.first_profile.id, wall_ms=1000, calls=[call("jd_extract", 1000)])
    store(
        reports,
        career.first_profile.id,
        wall_ms=9000,
        calls=[call("evidence_grade", 9000)],
        kind="recommendation",
    )
    store(
        reports,
        career.first_profile.id,
        wall_ms=5000,
        calls=[call("evidence_grade", 5000)],
        kind="attempt",
    )

    latency_report.cmd_report("7d", None, "all")
    assert "analyses: 3" in capsys.readouterr().out

    latency_report.cmd_report("7d", None, "attempt")
    out = capsys.readouterr().out
    assert "analyses: 1" in out and "max 5.0s" in out
