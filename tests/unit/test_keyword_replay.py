"""`scripts/keyword_replay.py`: what K2 would do to the stored reports (PRD F5.5.3).

Synthetic reports on the test's SQLite: the K1 column is the value the report stored,
K2 is recomputed over the same track, the Job Match move is the Keywords weight times
the change, and the footer is the median and the range of those changes. A report the
script cannot replay is counted as skipped, never guessed at.
"""

from contextlib import contextmanager
from decimal import Decimal

import pytest

import scripts.keyword_replay as keyword_replay
from src.applications import create_application
from src.bullets import create_bullet
from src.jd import StructuredJD
from src.tracks import create_track, set_track_bullets

# Five meaningful words and more: not what a recruiter types, so K2 drops it.
LONG = "cinco años de experiencia construyendo tableros en power bi para finanzas"


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

    monkeypatch.setattr(keyword_replay, "session_scope", scope)
    return session


def track_with(session, career, name: str, text: str):
    track = create_track(
        career.first_profile.id, session, name=name, applies_when="Para la prueba", lang="es"
    )
    bullet = create_bullet(
        career.first_profile.id,
        session,
        role_id=career.first_role.id,
        text_es=text,
        text_en=None,
        chips=[],
    )
    set_track_bullets(career.first_profile.id, session, track.id, [bullet.id])
    session.commit()
    return track


def store(session, career, track, *, stored: float, capped: int):
    report = {
        "jd": StructuredJD(
            title="Analista de datos",
            language="es",
            must_have=["python"],
            raw_keywords=["reportes", LONG],
        ).model_dump(mode="json"),
        "score": {
            "weights_version": "w4",
            "capped": capped,
            "sub_scores": {
                "keywords": {"value": stored, "matched": [], "missing": [], "detail": {}}
            },
        },
        "track": {"id": str(track.id), "name": track.name},
    }
    application = create_application(
        career.first_profile.id,
        session,
        jd_text="Una oferta",
        jd_hash="sha256:synthetic",
        report=report,
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    session.commit()
    return application


@pytest.fixture
def two_reports(reports, career):
    """Zeta evidences both kept terms; Alfa evidence none of them."""
    matches = store(
        reports,
        career,
        track_with(reports, career, "Zeta", "Automaticé reportes con Python"),
        stored=0.5,
        capped=50,
    )
    misses = store(
        reports,
        career,
        track_with(reports, career, "Alfa", "Cuidé plantas y ordené la oficina"),
        stored=0.2,
        capped=40,
    )
    return matches, misses


def test_the_line_shows_k1_k2_the_move_and_the_job_match(reports, two_reports, capsys):
    assert keyword_replay.cmd_report("30d") == 0

    out = capsys.readouterr().out
    assert "Analista de datos" in out
    assert (
        "K1 0.500  K2 1.000  +0.500  JM 50.0 → 57.5  terms 2 kept/1 dropped" in out
    ), "the kept terms score 1.0 and the long one is dropped"
    assert "K1 0.200  K2 0.000  -0.200  JM 40.0 → 37.0  terms 2 kept/1 dropped" in out
    assert "reports: 2   median change +0.150   range -0.200 .. +0.500" in out


def test_a_report_it_cannot_replay_is_counted_not_guessed(reports, career, two_reports, capsys):
    create_application(
        career.first_profile.id,
        reports,
        jd_text="Otra oferta",
        jd_hash="sha256:other",
        report={},
        weights_version="w4",
        prompt_versions={},
        token_cost_usd=Decimal("0"),
    )
    reports.commit()

    keyword_replay.cmd_report("30d")

    out = capsys.readouterr().out
    assert "reports: 2" in out
    assert "skipped (no keywords sub-score or document): 1" in out


def test_detail_names_the_matched_missing_and_dropped_lists(reports, two_reports, capsys):
    matches, misses = two_reports

    assert keyword_replay.cmd_detail(str(matches.id)) == 0
    out = capsys.readouterr().out
    assert "matched: python, reportes" in out
    assert "missing: (none)" in out
    assert f"dropped: {LONG}" in out
    assert "K1 0.500  K2 1.000  +0.500" in out

    assert keyword_replay.cmd_detail(str(misses.id)) == 0
    out = capsys.readouterr().out
    assert "matched: (none)" in out
    assert "missing: python, reportes" in out


def test_detail_says_so_when_the_application_or_its_keywords_are_missing(reports, capsys):
    assert keyword_replay.cmd_detail("00000000-0000-0000-0000-000000000000") == 1
    assert "no application" in capsys.readouterr().out
