"""WCAG contrast of the visual system's tokens (design v3, `q_design_v3.md` §1 and §6).

The values are parsed from the `:root` block of `src/web/static/src.css`, so the test fails
when a token is edited to something unreadable. Ratios follow WCAG 2.x: 4.5:1 for text,
3:1 for fills, outlines and dashed borders. Ash and stone are not text colours: ash is
exempt (disabled text), stone is decorative, and no template may use them as text.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC_CSS = ROOT / "src" / "web" / "static" / "src.css"
TEMPLATES = ROOT / "src" / "web" / "templates"

TEXT = 4.5
NON_TEXT = 3.0


def _root_tokens() -> dict[str, str]:
    css = SRC_CSS.read_text(encoding="utf-8")
    block = re.search(r":root\s*\{(.*?)\n\}", css, re.S)
    assert block, ":root block missing from src.css"
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b", block.group(1)))


TOKENS = _root_tokens()


def _luminance(token: str) -> float:
    value = TOKENS[token].lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(value[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


PAGE_SURFACES = ["paper", "vellum"]


def test_every_token_is_defined():
    expected = {
        "paper", "vellum", "hairline", "stone", "ash", "slate", "pewter", "ink",
        "forest", "lime", "highlight",
    }  # fmt: skip
    assert expected <= set(TOKENS)


def test_the_withdrawn_tokens_are_gone():
    withdrawn = {
        "canvas", "card", "sheet", "surface-2", "ink-2", "ink-3", "soft-green", "link", "focus",
        "score-strong", "score-adequate", "score-weak", "sev-blocker", "sev-warning", "sev-info",
        "highlight-base", "highlight-intense",
    }  # fmt: skip
    assert not withdrawn & set(TOKENS)


@pytest.mark.parametrize("surface", PAGE_SURFACES)
@pytest.mark.parametrize("text", ["ink", "pewter", "slate"])
def test_text_tiers_on_paper_and_vellum(text, surface):
    assert ratio(text, surface) >= TEXT, (text, surface, ratio(text, surface))


@pytest.mark.parametrize("highlight", ["lime", "highlight"])
def test_ink_on_the_highlighter(highlight):
    assert ratio("ink", highlight) >= TEXT, (highlight, ratio("ink", highlight))


def test_pewter_on_lime():
    assert ratio("pewter", "lime") >= TEXT, ratio("pewter", "lime")


def test_white_on_forest():
    assert ratio("paper", "forest") >= TEXT, ratio("paper", "forest")


@pytest.mark.parametrize("surface", PAGE_SURFACES)
def test_forest_is_visible_as_focus_ring_and_segments(surface):
    assert ratio("forest", surface) >= NON_TEXT, (surface, ratio("forest", surface))


def test_slate_dashed_border_of_a_missing_term_is_visible_on_paper():
    assert ratio("slate", "paper") >= NON_TEXT


def test_ash_is_below_text_contrast():
    # Documents why ash is for disabled text only: it must never be promoted to text.
    assert ratio("ash", "paper") < TEXT


def _template_text_classes() -> list[tuple[str, str]]:
    pattern = re.compile(r"(?<![\w-])(?:[\w\[\]-]+:)*text-(?:ash|stone)(?![\w-])")
    hits = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            hits.append((str(path.relative_to(ROOT)), match.group(0)))
    return hits


def test_no_template_uses_ash_or_stone_as_text():
    assert _template_text_classes() == []


def test_no_template_uses_the_withdrawn_button_and_severity_fills():
    """Design v3 §4: buttons are .btn variants; a destructive one is an ink outline, never
    a `bg-link text-bg` or `bg-sev-*` fill (S2b)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "web"
    offenders = [
        path.name
        for path in root.rglob("*.html")
        if "bg-link" in path.read_text(encoding="utf-8")
        or "bg-sev-" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
