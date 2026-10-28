"""WCAG contrast of the visual system's tokens (design v3, `q_design_v3.md` §1 and §6).

The values are parsed from the `:root` block (light) and the `:root[data-theme="dark"]` block
(dark) of `src/web/static/src.css`, so the test fails when a token is edited to something
unreadable in either theme. Ratios follow WCAG 2.x: 4.5:1 for text, 3:1 for fills, outlines and
dashed borders. Ash and stone are not text colours: ash is exempt (disabled text), stone is
decorative, and no template may use them as text.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC_CSS = ROOT / "src" / "web" / "static" / "src.css"
TEMPLATES = ROOT / "src" / "web" / "templates"

TEXT = 4.5
NON_TEXT = 3.0


def _block_tokens(selector: str) -> dict[str, str]:
    css = SRC_CSS.read_text(encoding="utf-8")
    block = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", css, re.S)
    assert block, f"{selector} block missing from src.css"
    tokens = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\b", block.group(1)))
    # Text on forest is white in both themes (the primary button's label), so it is a token too.
    return {**tokens, "white": "#ffffff"}


THEMES = {
    "light": _block_tokens(":root"),
    "dark": _block_tokens(':root[data-theme="dark"]'),
}
TOKENS = THEMES["light"]


def _luminance(token: str, tokens: dict[str, str]) -> float:
    value = tokens[token].lstrip("#")
    channels = []
    for i in (0, 2, 4):
        c = int(value[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def ratio(a: str, b: str, tokens: dict[str, str] = TOKENS) -> float:
    hi, lo = sorted((_luminance(a, tokens), _luminance(b, tokens)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


PAGE_SURFACES = ["paper", "vellum"]
THEME_NAMES = ["light", "dark"]


def test_every_token_is_defined():
    expected = {
        "paper", "vellum", "hairline", "stone", "ash", "slate", "pewter", "ink",
        "forest", "forest-ink", "lime", "highlight", "ochre", "brick", "on-lime",
    }  # fmt: skip
    for tokens in THEMES.values():
        assert expected <= set(tokens)


def test_the_withdrawn_tokens_are_gone():
    withdrawn = {
        "canvas", "card", "sheet", "surface-2", "ink-2", "ink-3", "soft-green", "link", "focus",
        "score-strong", "score-adequate", "score-weak", "sev-blocker", "sev-warning", "sev-info",
        "highlight-base", "highlight-intense",
    }  # fmt: skip
    assert not withdrawn & set(TOKENS)


@pytest.mark.parametrize("theme", THEME_NAMES)
@pytest.mark.parametrize("surface", PAGE_SURFACES)
@pytest.mark.parametrize("text", ["ink", "pewter", "slate", "forest-ink"])
def test_text_tiers_on_paper_and_vellum(theme, text, surface):
    tokens = THEMES[theme]
    assert ratio(text, surface, tokens) >= TEXT, (text, surface, ratio(text, surface, tokens))


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_ink_on_the_highlighter(theme):
    tokens = THEMES[theme]
    assert ratio("ink", "highlight", tokens) >= TEXT, ratio("ink", "highlight", tokens)


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_on_lime_is_the_text_on_the_intense_highlighter(theme):
    tokens = THEMES[theme]
    assert ratio("on-lime", "lime", tokens) >= TEXT, ratio("on-lime", "lime", tokens)


def test_pewter_on_lime():
    assert ratio("pewter", "lime") >= TEXT, ratio("pewter", "lime")


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_white_on_forest(theme):
    tokens = THEMES[theme]
    assert ratio("white", "forest", tokens) >= TEXT, ratio("white", "forest", tokens)


@pytest.mark.parametrize("theme", THEME_NAMES)
@pytest.mark.parametrize("surface", PAGE_SURFACES)
def test_forest_is_visible_as_focus_ring_and_segments(theme, surface):
    tokens = THEMES[theme]
    assert ratio("forest", surface, tokens) >= NON_TEXT, (surface, ratio("forest", surface, tokens))


@pytest.mark.parametrize("theme", THEME_NAMES)
@pytest.mark.parametrize("surface", PAGE_SURFACES)
@pytest.mark.parametrize("band", ["ochre", "brick"])
def test_the_two_other_score_bands_are_text_colours(theme, band, surface):
    """Design v3 §4: the Adecuado and Débil numbers, band words and sub-score bars take
    ochre and brick, so both must read as text on paper and on vellum."""
    tokens = THEMES[theme]
    assert ratio(band, surface, tokens) >= TEXT, (band, surface, ratio(band, surface, tokens))


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_slate_dashed_border_of_a_missing_term_is_visible_on_paper(theme):
    tokens = THEMES[theme]
    assert ratio("slate", "paper", tokens) >= NON_TEXT


@pytest.mark.parametrize("theme", THEME_NAMES)
def test_ash_is_below_text_contrast(theme):
    # Documents why ash is for disabled text only: it must never be promoted to text.
    tokens = THEMES[theme]
    assert ratio("ash", "paper", tokens) < TEXT


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
