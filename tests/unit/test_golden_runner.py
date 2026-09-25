"""The golden-set runner (queue A.3, amended by resume §2–§4).

The whole run happens offline against the fixture database: the provider is
stubbed at `client._post` and the runner's `session_scope` points at the test
engine, so no test ever opens a real database and no engine is created before
the production guard has spoken.
"""

import csv
from decimal import Decimal
from types import SimpleNamespace

import pytest

from scripts import golden_run
from src.config import get_settings
from src.extract import client as extract_client
from src.models import Application, Bullet, LlmCall, Profile, Role, Skill, Summary, User
from tests import golden_support as support

HEADER = [
    "pair_id",
    "profile",
    "split",
    "lang",
    "track",
    "weights_version",
    "score",
    "uncapped",
    "cap",
    "skills",
    "experience",
    "title",
    "keywords",
    "skills_direct",
    "skills_transfer",
    "cost_usd",
    "cached_calls",
    "application_id",
    "commit",
]

PRODUCTION_URL = "postgresql://user:pass@REDACTED-PROD-ENDPOINT/db"


@pytest.fixture
def run_env(test_settings, monkeypatch):
    """Settings a developer's .env would supply, plus the URL the runner resolves."""
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    get_settings.cache_clear()


@pytest.fixture
def provider(monkeypatch, run_env):
    stub = support.Provider()
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


@pytest.fixture
def script_session(session_factory, monkeypatch):
    monkeypatch.setattr(golden_run, "session_scope", lambda: support.session_from(session_factory))
    return session_factory


def cv_file(tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(support.docx_bytes("Experiencia", "Reduje el cierre un 30% con Python"))
    return path


def test_the_production_guard_refuses_before_an_engine_exists(monkeypatch, test_settings, capsys):
    """A.3 step 1: the production endpoint is refused with no flag to override it."""
    monkeypatch.setenv("DATABASE_URL", PRODUCTION_URL)
    get_settings.cache_clear()
    engines: list[int] = []

    def bomb():
        engines.append(1)
        raise AssertionError("the runner created an engine before the production guard")

    monkeypatch.setattr("src.db.get_engine", bomb)

    result = golden_run.main(["--label", "w3"])

    out = capsys.readouterr().out
    assert result != 0
    assert "production" in out
    assert engines == [], "no engine may be created when the host is production"


def test_missing_configuration_names_the_variable_and_the_worktree(
    tmp_path, monkeypatch, test_settings, capsys
):
    """Resume §4: the runner never reads .env itself, so absence is said out loud.

    The empty directory is a worktree without its own .env: `src.config` reads
    `.env` from the working directory and there is none to read here.
    """
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    get_settings.cache_clear()

    assert golden_run.main(["--label", "w3"]) == 2

    out = capsys.readouterr().out
    assert "DATABASE_URL" in out and "OPENROUTER_API_KEY" in out
    assert "worktree" in out and ".env" in out


def test_the_output_must_land_in_a_gitignored_path(tmp_path, run_env, capsys):
    """A.3 step 5: `git check-ignore` must match the path the file lands in."""
    assert golden_run.main(["--label", "w3", "--out", str(tmp_path / "run.csv")]) == 2

    assert "gitignored" in capsys.readouterr().out


def test_the_csv_has_the_documented_columns_and_the_test_split_stays_sealed(
    tmp_path, session, two_accounts, vocabulary, provider, script_session
):
    """A.3 step 5: one row per dev pair, test rows neither read nor written."""
    (ana, ana_profile), (bea, bea_profile) = two_accounts
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, profile="Ana", cv_version="CV-1"),
            support.row(2, profile="Ana", cv_version="CV-1"),
            # The test-only profile is unmapped on purpose: without --include-test
            # that is not an error (resume §2) and the row is never read.
            support.row(3, profile="Bea", cv_version="CV-9", split="test"),
        ],
    )
    mapping = support.write_map(
        tmp_path / "map.toml", profiles={"Ana": ana.email}, cvs={"CV-1": str(cv_file(tmp_path))}
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"

    result = golden_run.main(
        ["--label", "w3", "--sheet", str(sheet), "--map", str(mapping), "--out", str(out)]
    )

    assert result == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert not lines[0].startswith("#"), "the sealed split leaves no comment line"
    assert lines[0].split(",") == HEADER
    rows = list(csv.DictReader(lines))
    assert [entry["pair_id"] for entry in rows] == ["1", "2"]
    assert all(entry["split"] == "dev" for entry in rows)
    assert all(entry["profile"] == "Ana" and entry["track"] == "CV-1" for entry in rows)
    assert all(entry["weights_version"] == "w3" for entry in rows)
    assert all(entry["application_id"] and entry["commit"] for entry in rows)
    assert rows[0]["skills_transfer"] != "", "w3 computes the split (F5.5.1)"
    assert session.query(Application).count() == 2
    assert session.query(Bullet).filter(Bullet.profile_id == bea_profile.id).count() == 0


def test_opening_the_test_split_marks_the_csv_and_writes_its_rows(
    tmp_path, session, two_accounts, vocabulary, provider, script_session
):
    (ana, ana_profile), (bea, bea_profile) = two_accounts
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, profile="Ana", cv_version="CV-1"),
            support.row(2, profile="Bea", cv_version="CV-2", split="test"),
        ],
    )
    mapping = support.write_map(
        tmp_path / "map.toml",
        profiles={"Ana": ana.email, "Bea": bea.email},
        cvs={"CV-1": str(cv_file(tmp_path)), "CV-2": str(cv_file(tmp_path))},
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"

    result = golden_run.main(
        [
            "--label",
            "w3",
            "--include-test",
            "--sheet",
            str(sheet),
            "--map",
            str(mapping),
            "--out",
            str(out),
        ]
    )

    assert result == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("#") and "test split opened" in lines[0]
    rows = list(csv.DictReader(lines[1:]))
    assert [entry["pair_id"] for entry in rows] == ["1", "2"]
    assert {entry["split"] for entry in rows} == {"dev", "test"}


def test_wipe_touches_only_the_profiles_the_in_scope_rows_use(
    tmp_path, session, two_accounts, career, vocabulary, provider, script_session
):
    """Resume §2: a profile that appears only in test rows is neither read nor wiped."""
    (ana, ana_profile), (bea, bea_profile) = two_accounts
    ana_profile.headline = "Camarero de eventos"
    ana_profile.skills = ["python"]
    session.add(Summary(profile_id=ana_profile.id, lang="es", text="una síntesis"))
    session.add(
        LlmCall(
            purpose="resume_extract",
            prompt_version="v1",
            model="test/model-v1",
            input_hash="0" * 64,
            response_json={},
        )
    )
    session.commit()
    old_bullet = career.first_bullet.id
    bea_bullets = session.query(Bullet).filter(Bullet.profile_id == bea_profile.id).count()
    bea_roles = session.query(Role).filter(Role.profile_id == bea_profile.id).count()

    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, profile="Ana", cv_version="CV-1"),
            support.row(2, profile="Bea", cv_version="CV-9", split="test"),
        ],
    )
    mapping = support.write_map(
        tmp_path / "map.toml", profiles={"Ana": ana.email}, cvs={"CV-1": str(cv_file(tmp_path))}
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"

    result = golden_run.main(
        [
            "--label",
            "w3",
            "--wipe",
            "--yes",
            "--sheet",
            str(sheet),
            "--map",
            str(mapping),
            "--out",
            str(out),
        ]
    )

    assert result == 0
    session.expire_all()
    # The mapped profile's old career data is gone (the run imports new data below;
    # the wipe's own effect on summaries and profile fields is unit-tested)…
    assert session.query(Bullet).filter(Bullet.id == old_bullet).count() == 0
    # …while the test-only profile's rows, the logins and the ledger survive.
    assert session.query(Bullet).filter(Bullet.profile_id == bea_profile.id).count() == bea_bullets
    assert session.query(Role).filter(Role.profile_id == bea_profile.id).count() == bea_roles
    assert session.query(User).count() == 2
    assert session.query(Profile).count() == 2
    assert session.query(LlmCall).filter(LlmCall.input_hash == "0" * 64).count() == 1
    assert session.query(Skill).filter(Skill.canonical == "python").count() == 1
    assert session.query(Application).count() == 1, "only the dev pair is analysed"


def test_a_wipe_requires_the_typed_word(
    tmp_path, session, two_accounts, career, provider, script_session, monkeypatch
):
    """A.3 step 2: without --yes the operator types DELETE or nothing happens."""
    monkeypatch.setattr("builtins.input", lambda prompt: "no")
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx", [support.row(1, profile="Ana", cv_version="CV-1")]
    )
    mapping = support.write_map(
        tmp_path / "map.toml",
        profiles={"Ana": two_accounts[0][0].email},
        cvs={"CV-1": str(cv_file(tmp_path))},
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"

    result = golden_run.main(
        [
            "--label",
            "w3",
            "--wipe",
            "--sheet",
            str(sheet),
            "--map",
            str(mapping),
            "--out",
            str(out),
        ]
    )

    assert result == 1
    session.expire_all()
    kept = session.query(Bullet).filter(Bullet.id == career.first_bullet.id).count()
    assert kept == 1, "an unconfirmed wipe deletes nothing"


def test_wipe_blanks_the_profile_row_and_keeps_the_login(session, two_accounts, career):
    """A.3 step 2: the row survives blanked; the login, the ledger and vocabulary do not move."""
    (ana, ana_profile), (bea, bea_profile) = two_accounts
    ana_profile.headline = "Camarero de eventos"
    ana_profile.summary = "Cinco años de oficio."
    ana_profile.skills = ["python"]
    ana_profile.standing_risks = ["salto de industria"]
    session.add(Summary(profile_id=ana_profile.id, lang="es", text="una síntesis"))
    session.add(
        LlmCall(
            purpose="resume_extract",
            prompt_version="v1",
            model="test/model-v1",
            input_hash="0" * 64,
            response_json={},
        )
    )
    session.commit()

    counts = golden_run.wipe_profile(session, ana_profile.id)
    session.commit()

    assert counts["profile_blanked"] == 1
    assert counts["bullets"] == 1 and counts["summaries"] == 2
    session.expire_all()
    ana_profile = session.get(Profile, ana_profile.id)
    assert ana_profile.headline is None and ana_profile.summary is None
    assert ana_profile.skills == [] and ana_profile.standing_risks == []
    assert session.get(User, ana.id) is not None
    assert session.query(LlmCall).filter(LlmCall.input_hash == "0" * 64).count() == 1
    assert session.query(Skill).filter(Skill.canonical == "python").count() == 1
    assert session.query(Summary).filter(Summary.profile_id == bea_profile.id).count() == 1


def test_a_w2_report_leaves_the_split_columns_blank():
    """w2 computes no direct/transfer split (verified at ebac5ca): blank, not invented."""
    analysis = SimpleNamespace(
        report={
            "score": {
                "capped": 71,
                "uncapped": 71,
                "cap": None,
                "sub_scores": {
                    "skills": {"value": 0.6, "detail": {}},
                    "experience": {"value": 0.8, "detail": {}},
                    "title": {"value": 0.5, "detail": {}},
                    "keywords": {"value": 0.7, "detail": {}},
                },
            },
            "llm": {"calls": [{"cached": True}, {"cached": False}]},
        },
        weights_version="w2",
        cost_usd=Decimal("0.000123"),
    )
    pair = SimpleNamespace(pair_id="1", profile="Ana", split="dev", lang="es")
    application = SimpleNamespace(id="app-1")

    names = ("skills", "experience", "title", "keywords")
    row = golden_run.csv_row(pair, analysis, application, "CV-1", "deadbeef", names)

    assert row["skills_direct"] == "" and row["skills_transfer"] == ""
    assert row["cached_calls"] == 1
    assert row["score"] == 71 and row["cap"] == ""
