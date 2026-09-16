"""The two architectural rules of PRD 5.1, enforced instead of documented.

`score/` may not make network calls and `parse/` may not import `extract/`. Reading
the imports is the only way to keep that true as the code grows, because the rule
is about what does *not* appear.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src"
NETWORK_MODULES = {"httpx", "requests", "aiohttp", "urllib.request", "openai", "src.extract"}


def imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def package_files(package: str) -> list[Path]:
    return sorted((ROOT / package).rglob("*.py"))


def test_score_makes_no_network_calls():
    for path in package_files("score"):
        offenders = imports_of(path) & NETWORK_MODULES
        assert not offenders, f"{path.name} imports {offenders}"


def test_parse_does_not_import_extract():
    for path in package_files("parse"):
        assert not any(
            module == "src.extract" or module.startswith("src.extract.")
            for module in imports_of(path)
        ), f"{path.name} imports src.extract"


def test_extract_does_not_import_score_or_parse():
    """The model edge must not depend on the deterministic core either."""
    for path in package_files("extract"):
        assert not any(
            module in {"src.score", "src.parse"} or module.startswith(("src.score.", "src.parse."))
            for module in imports_of(path)
        ), f"{path.name} imports the deterministic core"
