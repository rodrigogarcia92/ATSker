"""R.1: the history scan finds planted data, masks it, and rewrites nothing.

The repository built here is a real temporary git repository, because the thing under
test is `git log --all -p` parsing — a fake would test the fake.
"""

import subprocess
from pathlib import Path

import pytest

from scripts import history_scan


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")
    git(path, "config", "user.email", "scan@example.com")
    git(path, "config", "user.name", "Scan")
    return path


def commit(repo: Path, name: str, content: str, message: str = "add") -> None:
    (repo / name).write_text(content, encoding="utf-8")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)


def test_a_planted_email_and_key_are_found_and_masked(repo, tmp_path):
    commit(
        repo,
        "notes.txt",
        "contact: real.person@gmail.com\nOPENAI_API_KEY=sk-abcdef0123456789abcdef\n",
    )
    out = tmp_path / "scan.md"

    code = history_scan.main(["--repo", str(repo), "--out", str(out)])

    assert code == 1
    report = out.read_text(encoding="utf-8")
    assert "re…" in report and "sk…" in report
    assert "real.person@gmail.com" not in report
    assert "sk-abcdef0123456789abcdef" not in report
    assert "email: 1" in report and "openai-key: 1" in report


def test_a_clean_repo_exits_zero(repo, tmp_path):
    commit(repo, "notes.txt", "Nothing personal here, just prose.\n")
    out = tmp_path / "scan.md"

    assert history_scan.main(["--repo", str(repo), "--out", str(out)]) == 0
    assert "nothing found" in out.read_text(encoding="utf-8")


def test_example_and_test_domains_are_not_personal_data(repo, tmp_path):
    commit(repo, "notes.txt", "persona@example.com and bea@acme.test\n")
    out = tmp_path / "scan.md"

    assert history_scan.main(["--repo", str(repo), "--out", str(out)]) == 0


def test_credentials_and_a_dni_are_found(repo, tmp_path):
    commit(
        repo,
        "notes.txt",
        "DATABASE_URL=postgresql://ana:s3cretpass@db.example.net/x\nDNI 12345678\n",
    )
    out = tmp_path / "scan.md"

    assert history_scan.main(["--repo", str(repo), "--out", str(out)]) == 1
    report = out.read_text(encoding="utf-8")
    assert "postgres-credentials: 1" in report
    assert "dni: 1" in report


def test_a_name_from_the_local_list_is_found_masked(repo, tmp_path):
    commit(repo, "notes.txt", "Prepared by Rodrigo.\n")
    names = tmp_path / "local_names.txt"
    names.write_text("# the operator's names\nRodrigo\n", encoding="utf-8")
    out = tmp_path / "scan.md"

    code = history_scan.main(
        ["--repo", str(repo), "--names", str(names), "--out", str(out)]
    )

    assert code == 1
    report = out.read_text(encoding="utf-8")
    assert "Ro…" in report
    assert "Rodrigo" not in report, "the report never carries the raw name"


def test_the_scan_rewrites_nothing(repo, tmp_path):
    commit(repo, "notes.txt", "real.person@gmail.com\n")
    before = git(repo, "rev-parse", "HEAD")

    history_scan.main(["--repo", str(repo), "--out", str(tmp_path / "scan.md")])

    assert git(repo, "rev-parse", "HEAD") == before
    assert git(repo, "status", "--porcelain").strip() == "", "no file was touched"


def test_an_iso_date_is_not_a_phone(repo, tmp_path):
    commit(repo, "notes.txt", "Created 2026-09-27 and updated 2026-10-01.\n")
    out = tmp_path / "scan.md"

    assert history_scan.main(["--repo", str(repo), "--out", str(out)]) == 0


def test_a_human_formatted_phone_is_found(repo, tmp_path):
    commit(repo, "notes.txt", "Call ++00 111 222 333 to confirm.\n")
    out = tmp_path / "scan.md"

    assert history_scan.main(["--repo", str(repo), "--out", str(out)]) == 1
    assert "phone: 1" in out.read_text(encoding="utf-8")
