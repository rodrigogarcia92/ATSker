"""The golden-set runner (queue A.3, amended by resume §2–§4).

The whole run happens offline against the fixture database: the provider is
stubbed at `client._post` and the runner's `session_scope` points at the test
engine, so no test ever opens a real database and no engine is created before
the production guard has spoken.
"""

import argparse
import csv
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import golden_run, golden_stats
from src.config import get_settings
from src.extract import client as extract_client
from src.models import (
    Application,
    Bullet,
    LlmCall,
    Profile,
    Resume,
    Role,
    Skill,
    Summary,
    Track,
    User,
)
from src.roles import create_role
from src.tracks import create_track, set_track_active
from tests import golden_support as support

HEADER = [
    "pair_id",
    "profile",
    "split",
    "lang",
    "track",
    "weights_version",
    "vocabulary_hash",
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
    "model",
    "reasoning_effort",
    "application_id",
    "commit",
]

PRODUCTION_URL = "postgresql://user:pass@ep-prod-fake-0000.example.invalid/db"


@pytest.fixture(autouse=True)
def _settings_cache_reset():
    # The guard reads cached settings, so a fragment set by one test must not leak into the next.
    yield
    get_settings.cache_clear()


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
    monkeypatch.setenv("PROD_DB_HOST_FRAGMENT", "ep-prod-fake")
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


def _golden_guard(monkeypatch, url: str, fragment: str) -> str | None:
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PROD_DB_HOST_FRAGMENT", fragment)
    get_settings.cache_clear()
    return golden_run.production_guard()


def test_the_golden_guard_refuses_a_host_containing_the_fragment(monkeypatch):
    reason = _golden_guard(monkeypatch, PRODUCTION_URL, "ep-prod-fake")
    assert reason is not None
    assert "--prod" not in reason, "golden runs have no override"
    assert "ep-prod-fake" not in reason


def test_the_golden_guard_refuses_a_non_local_host_when_the_fragment_is_unset(monkeypatch):
    # An empty value counts as unset, and it overrides any value in a developer's .env.
    reason = _golden_guard(
        monkeypatch, "postgresql://user:pass@ep-dev-fake-0000.example.invalid/db", ""
    )
    assert reason is not None
    assert "PROD_DB_HOST_FRAGMENT" in reason


def test_the_golden_guard_allows_a_local_host_when_the_fragment_is_unset(monkeypatch):
    assert _golden_guard(monkeypatch, "sqlite://", "") is None
    assert _golden_guard(monkeypatch, "postgresql://user:pass@localhost/db", "") is None


def test_the_golden_guard_allows_a_different_non_local_host(monkeypatch):
    reason = _golden_guard(
        monkeypatch, "postgresql://user:pass@ep-dev-fake-0000.example.invalid/db", "ep-prod-fake"
    )
    assert reason is None


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
    assert all(entry["weights_version"] == "w5" for entry in rows)
    assert all(entry["vocabulary_hash"].startswith("sha256:") for entry in rows)
    assert all(entry["application_id"] and entry["commit"] for entry in rows)
    assert rows[0]["skills_transfer"] != "", "w3 computes the split (F5.5.1)"
    assert session.query(Application).count() == 2
    assert session.query(Bullet).filter(Bullet.profile_id == bea_profile.id).count() == 0


def run_with(tmp_path, two_accounts, argv: list[str]) -> tuple[int, Path]:
    """One offline run over a single dev pair, returning its exit code and CSV."""
    (ana, _), _ = two_accounts
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx", [support.row(1, profile="Ana", cv_version="CV-1")]
    )
    mapping = support.write_map(
        tmp_path / "map.toml", profiles={"Ana": ana.email}, cvs={"CV-1": str(cv_file(tmp_path))}
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"
    result = golden_run.main(
        ["--sheet", str(sheet), "--map", str(mapping), "--out", str(out), *argv]
    )
    return result, out


def test_the_second_model_reaches_every_call_and_the_csv_columns_carry_it(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, monkeypatch
):
    """PRD §11: `--model`/`--effort` go to the résumé import and to `analyze`, and
    the CSV reports what the calls were actually made with."""
    monkeypatch.setattr("builtins.input", lambda prompt: "YES")

    result, out = run_with(
        tmp_path, two_accounts, ["--label", "w4", "--model", "x", "--effort", "medium"]
    )

    assert result == 0
    assert provider.calls, "the run reached the provider"
    assert {call["model"] for call in provider.calls} == {"x"}
    assert {call["reasoning"]["effort"] for call in provider.calls} == {"medium"}
    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert {row["model"] for row in rows} == {"x"}
    assert {row["reasoning_effort"] for row in rows} == {"medium"}


def test_the_second_model_is_confirmed_before_the_first_call(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, monkeypatch
):
    """A.6: it may cost far more than the default, so nothing is spent unconfirmed."""
    monkeypatch.setattr("builtins.input", lambda prompt: "no")

    result, _out = run_with(tmp_path, two_accounts, ["--label", "w4", "--model", "x"])

    assert result == 1
    assert provider.calls == [], "no call was made"


@pytest.mark.parametrize("label", ["w3", "w4", "w4-vocab", "w10-x2"])
def test_a_label_names_the_scorer_being_measured(label):
    assert golden_run.run_label(label) == label


@pytest.mark.parametrize("label", ["w4_vocab", "W4", "v4", "w4-", "w4-Vocab", "x"])
def test_a_label_that_is_not_a_scorer_name_is_refused(label):
    with pytest.raises(argparse.ArgumentTypeError):
        golden_run.run_label(label)


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


def test_a_run_imports_two_cvs_tracks_named_after_cv_version_and_writes_the_csv(
    tmp_path, session, two_accounts, vocabulary, provider, script_session
):
    """A.5: the whole pipeline against the fixture database, offline.

    Two CVs import once each; the tracks take the sheet's `cv_version` verbatim;
    every dev pair is analysed against its track and lands in the CSV with the
    application id the history will show.
    """
    (ana, ana_profile), (bea, bea_profile) = two_accounts
    first_cv = tmp_path / "cv-one.docx"
    first_cv.write_bytes(support.docx_bytes("Experiencia", "Cerré el mes un 30% más rápido"))
    second_cv = tmp_path / "cv-two.docx"
    second_cv.write_bytes(support.docx_bytes("Perfil", "Automatizé reportes con Python"))
    sheet = support.write_sheet(
        tmp_path / "sheet.xlsx",
        [
            support.row(1, profile="Ana", cv_version="CV-1"),
            support.row(2, profile="Ana", cv_version="CV-2"),
            support.row(3, profile="Ana", cv_version="CV-1"),
            support.row(4, profile="Bea", cv_version="CV-9", split="test"),
        ],
    )
    mapping = support.write_map(
        tmp_path / "map.toml",
        profiles={"Ana": ana.email},
        cvs={"CV-1": str(first_cv), "CV-2": str(second_cv)},
    )
    out = support.gitignored_dir(tmp_path) / "run.csv"

    result = golden_run.main(
        ["--label", "w3", "--sheet", str(sheet), "--map", str(mapping), "--out", str(out)]
    )

    assert result == 0
    # Two distinct (profile, cv_version) pairs → two archives, two named tracks.
    assert session.query(Resume).count() == 2
    tracks = session.query(Track).filter(Track.profile_id == ana_profile.id).all()
    assert sorted(track.name for track in tracks) == ["CV-1", "CV-2"]
    assert all(track.name in {"CV-1", "CV-2"} for track in tracks)
    # Every dev pair is analysed and persisted against its own track…
    applications = session.query(Application).all()
    assert len(applications) == 3
    by_track = {track.id: track.name for track in tracks}
    assert sorted(by_track[app.track_id] for app in applications) == ["CV-1", "CV-1", "CV-2"]
    # …and the CSV names the same tracks and the same applications.
    rows = list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()))
    assert [entry["pair_id"] for entry in rows] == ["1", "2", "3"]
    assert [entry["track"] for entry in rows] == ["CV-1", "CV-2", "CV-1"]
    assert {entry["application_id"] for entry in rows} == {str(app.id) for app in applications}
    assert session.query(Bullet).filter(Bullet.profile_id == bea_profile.id).count() == 0


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
            "llm": {
                "calls": [
                    {"cached": True, "model": "test/model-v1", "reasoning_effort": None},
                    {"cached": False, "model": "test/model-v1", "reasoning_effort": None},
                ]
            },
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
    assert row["model"] == "test/model-v1" and row["reasoning_effort"] == ""


def test_reuse_and_wipe_cannot_be_asked_for_at_once(monkeypatch, run_env):
    """R.1: one mode imports what the other analyses, so argparse settles it first."""
    engines: list[int] = []

    def bomb():
        engines.append(1)
        raise AssertionError("a usage error must not reach the database")

    monkeypatch.setattr("src.db.get_engine", bomb)

    with pytest.raises(SystemExit) as exit_info:
        golden_run.main(["--label", "w3", "--reuse", "--wipe"])

    assert exit_info.value.code == 2
    assert engines == [], "no engine may be created for a usage error"


def test_reuse_analyses_the_existing_track_and_imports_nothing(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, monkeypatch, capsys
):
    """R.1: the second run of the recipe — the database exactly as the operator left it.

    Nothing is imported, the pair is analysed against the track already named
    `cv_version`, and the CSV says where its rows came from — and `golden_stats`
    reads the file with that extra comment line in front of the header.
    """
    (_, ana_profile), _ = two_accounts
    track = create_track(ana_profile.id, session, name="CV-1")
    session.commit()

    def bomb(*args, **kwargs):
        raise AssertionError("--reuse must never import a CV")

    monkeypatch.setattr(golden_run, "import_cv", bomb)

    result, out = run_with(tmp_path, two_accounts, ["--label", "w4", "--reuse"])

    assert result == 0
    assert "reuse: analysing the tracks as they are; nothing imported" in capsys.readouterr().out
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# reuse: tracks analysed as found in the database, no import"
    assert lines[1].split(",") == HEADER
    rows = list(csv.DictReader(lines[1:]))
    assert [entry["pair_id"] for entry in rows] == ["1"]
    assert rows[0]["track"] == "CV-1" and rows[0]["commit"]
    session.expire_all()
    assert session.query(Resume).count() == 0, "nothing was imported"
    application = session.query(Application).one()
    assert application.track_id == track.id
    assert str(application.id) == rows[0]["application_id"]
    read_rows, sub_names = golden_stats.read_run(out)
    assert [entry["pair_id"] for entry in read_rows] == ["1"]
    assert sorted(sub_names) == ["experience", "keywords", "skills", "title"]


def test_reuse_skips_a_pair_with_no_active_track_of_that_name(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, capsys
):
    """R.1: no track to analyse means no row and no provider call."""
    result, out = run_with(tmp_path, two_accounts, ["--label", "w4", "--reuse"])

    assert result == 0
    assert "pair 1: skipped, no active track named 'CV-1'" in capsys.readouterr().out
    assert provider.calls == []
    assert session.query(Application).count() == 0
    assert list(csv.DictReader(out.read_text(encoding="utf-8").splitlines()[1:])) == []


def test_reuse_refuses_to_guess_between_two_active_tracks_of_one_name(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, capsys
):
    """R.1: two candidates are the operator's decision, not a sort order's."""
    _, ana_profile = two_accounts[0]
    create_track(ana_profile.id, session, name="CV-1")
    create_track(ana_profile.id, session, name="CV-1")
    session.commit()

    result, _out = run_with(tmp_path, two_accounts, ["--label", "w4", "--reuse"])

    assert result == 0
    printed = capsys.readouterr().out
    assert "pair 1: skipped, 2 active tracks named 'CV-1' — rename or deactivate one" in printed
    assert session.query(Application).count() == 0


def test_reuse_counts_only_active_tracks(
    tmp_path, session, two_accounts, vocabulary, provider, script_session, capsys
):
    """R.1: a duplicate the operator deactivated is not a candidate."""
    _, ana_profile = two_accounts[0]
    active = create_track(ana_profile.id, session, name="CV-1")
    retired = create_track(ana_profile.id, session, name="CV-1")
    set_track_active(ana_profile.id, session, retired.id, active=False)
    session.commit()

    result, _out = run_with(tmp_path, two_accounts, ["--label", "w4", "--reuse"])

    assert result == 0
    assert "skipped" not in capsys.readouterr().out
    session.expire_all()
    assert session.query(Application).one().track_id == active.id


def test_reuse_scores_the_title_the_operator_typed_in_the_app(
    tmp_path, session, two_accounts, vocabulary, provider, script_session
):
    """R.1: the hand edit is the input, and the stored report proves it was read.

    The extraction this runner would import proposes 'Data Scientist' for the
    role, so only a run that read the row as it stands can have matched 'risk'.
    """
    _, ana_profile = two_accounts[0]
    create_role(
        ana_profile.id,
        session,
        employer="Globex",
        title_es="Analista de datos",
        title_en="Risk Analyst",
    )
    create_track(ana_profile.id, session, name="CV-1")
    session.commit()
    proposal = json.loads(support.JD_PROPOSAL)
    proposal["language"] = "en"
    proposal["title"] = "Risk Manager"
    provider.answers["JDProposal"] = json.dumps(proposal)

    result, out = run_with(tmp_path, two_accounts, ["--label", "w4", "--reuse"])

    assert result == 0
    session.expire_all()
    report = session.query(Application).one().report
    title = report["score"]["sub_scores"]["title"]
    assert title["matched"] == ["risk"], "the English title the app holds is what was read"
    assert title["missing"] == ["manager"], "the posting's other word is not in the profile"
    row = next(csv.DictReader(out.read_text(encoding="utf-8").splitlines()[1:]))
    assert float(row["title"]) == 0.5
