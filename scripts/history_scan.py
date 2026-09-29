"""Scan every commit of every branch for personal data and secrets (PRD §14 N10, R.1).

The repository is expected to be published later and git history is forever (PRD
principle 5), so the check has to look at the history, not the working tree. This
walks `git log --all -p` and reports lines that look like an address, a phone, a
DNI, a URL with credentials, or an API key — plus any name listed in a **local,
gitignored** file passed with `--names`, because names cannot be pattern-matched.

It rewrites nothing: no rebase, no filter-branch, no amend. The report goes to
`fixtures/` (gitignored) with every match **masked** to its first two characters, so
the report itself cannot become the leak it exists to find. Exit code 1 means
something was found and a human has to decide what to do about it.

    uv run python scripts/history_scan.py --names fixtures/local_names.txt
"""

import argparse
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.normalize.text import fold

# A match is shown as its first two characters and an ellipsis: enough to recognise
# what was found, not enough to be the finding.
MASK_TAIL = "…"

# Domains that are not personal data: the fixtures and tests are full of them.
TEST_DOMAINS = ("example.com", "example.org", "example.net", "localhost")

# A phone is digits with a human separator or a country code: the raw digit run and the
# ISO date are not phones, and flagging the repository's dates as personal data would
# drown the real findings (R.1's report is only useful if it is reviewable).
_PHONE = re.compile(
    r"(?<![\w-])(?:\+\d{1,3}[ .-]?)?(?:\(?\d{2,4}\)?[ .-]){1,3}\d{2,4}(?![\w-])"
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone", _PHONE),
    ("dni", re.compile(r"\bDNI\b\D{0,6}\d{8}\b", re.IGNORECASE)),
    ("postgres-credentials", re.compile(r"\bpostgres(?:ql)?://[^:\s/]+:[^@\s/]+@", re.IGNORECASE)),
    ("url-credentials", re.compile(r"\b\w+://[^/\s:@]+:[^/\s@]+@")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}")),
    (
        "key-assignment",
        re.compile(r"""(?i)\b(?:key|token|secret|password|passwd|pwd)\b\s*[:=]\s*['"]?([A-Za-z0-9+/_\-]{16,})"""),
    ),
)

_COMMIT = "COMMIT:"
_HUNK = re.compile(r"\+(\d+)")


def _is_phone(text: str) -> bool:
    digits = "".join(char for char in text if char.isdigit())
    if not 7 <= len(digits) <= 15:
        return False
    return "+" in text or "(" in text or " " in text


@dataclass(frozen=True)
class Finding:
    """One matched line, as the report shows it — never the raw text."""

    commit: str
    path: str
    line: int
    pattern: str
    masked: str

    def as_row(self) -> str:
        return (
            f"| {self.commit[:12]} | {self.path} | {self.line} | {self.pattern} | "
            f"{self.masked} |"
        )


def mask(text: str) -> str:
    """The first two characters and an ellipsis — recognisable, not reproducible."""
    return text[:2] + MASK_TAIL


def _is_test_email(match: str) -> bool:
    domain = match.rpartition("@")[2].lower()
    return (
        domain in TEST_DOMAINS
        or domain.startswith("example.")
        or domain.endswith((".test", ".invalid", ".example"))
    )


def load_names(path: Path | None) -> list[str]:
    """The local name list, one per line; blank lines and `#` comments ignored."""
    if path is None or not path.exists():
        return []
    names = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        name = raw.strip()
        if name and not name.startswith("#"):
            names.append(name)
    return names


def _scan_line(commit: str, path: str, line: int, text: str, names: Sequence[str]) -> list[Finding]:
    """Every pattern this one added line matches, masked."""
    found: list[Finding] = []
    for pattern, regex in PATTERNS:
        for match in regex.finditer(text):
            hit = match.group(0)
            if pattern == "email" and _is_test_email(hit):
                continue
            if pattern == "phone" and not _is_phone(hit):
                continue
            found.append(Finding(commit, path, line, pattern, mask(hit)))
            break
    if names:
        folded = fold(text)
        for name in names:
            if fold(name) in folded:
                found.append(Finding(commit, path, line, "name", mask(name)))
    return found


def scan_history(repo: Path, names: Sequence[str]) -> list[Finding]:
    """Walk every commit of every branch, added lines only, and report the matches."""
    log = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "log",
            "--all",
            "--no-color",
            "--unified=0",
            "-p",
            f"--format={_COMMIT}%H",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    commit = ""
    path = ""
    line = 0
    findings: list[Finding] = []
    for raw in log.stdout.splitlines():
        if raw.startswith(_COMMIT):
            commit, path, line = raw[len(_COMMIT) :], "", 0
        elif raw.startswith("diff --git"):
            path = ""
        elif raw.startswith("+++ "):
            target = raw[4:].strip()
            path = target[2:] if target.startswith("b/") else ""
        elif raw.startswith("@@"):
            match = _HUNK.search(raw)
            line = int(match.group(1)) if match else 0
        elif raw.startswith("+") and not raw.startswith("+++"):
            findings.extend(_scan_line(commit, path, line, raw[1:], names))
            line += 1
    return findings


def render_report(findings: Sequence[Finding]) -> str:
    """Counts per pattern, then the masked rows; never the raw text."""
    counts = Counter(finding.pattern for finding in findings)
    lines = [
        "# Personal-data history scan",
        "",
        "Machine-generated by `scripts/history_scan.py`. `fixtures/` is gitignored, so",
        "this file is not committed; every match is masked.",
        "",
        "## Counts per pattern",
        "",
    ]
    for pattern in sorted(counts):
        lines.append(f"- {pattern}: {counts[pattern]}")
    if not counts:
        lines.append("- (nothing found)")
    lines += [
        "",
        "## Findings",
        "",
        "| commit | path | line | pattern | match |",
        "|---|---|---|---|---|",
    ]
    lines.extend(finding.as_row() for finding in findings)
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan the whole git history, masked.")
    parser.add_argument("--repo", default=".", help="repository to scan (default: .)")
    parser.add_argument("--names", help="local, gitignored file of names, one per line")
    parser.add_argument(
        "--out", default="fixtures/history_scan.md", help="report path (gitignored)"
    )
    args = parser.parse_args(argv)

    names = load_names(Path(args.names) if args.names else None)
    findings = scan_history(Path(args.repo), names)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(findings), encoding="utf-8")

    counts = Counter(finding.pattern for finding in findings)
    for pattern in sorted(counts):
        print(f"{pattern}: {counts[pattern]}")
    print(f"{len(findings)} finding(s); report at {out}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
