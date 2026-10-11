"""WCAG contrast of the visual system's tokens (PRD §12.6).

The values are parsed from the `:root` block of `src/web/static/src.css`, so the test fails
when a token is edited to something unreadable. Ratios follow WCAG 2.x: 4.5:1 for text,
3:1 for fills and outlines.
"""

import re
from pathlib import Path

import pytest

SRC_CSS = Path(__file__).resolve().parents[2] / "src" / "web" / "static" / "src.css"

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


LIGHT_SURFACES = ["canvas", "card", "sheet", "surface-2"]


def test_every_token_is_defined():
    expected = {
        "canvas", "card", "sheet", "surface-2", "hairline", "ink", "ink-2", "ink-3",
        "forest", "lime", "highlight-base", "highlight-intense", "soft-green",
        "score-strong", "score-adequate", "score-weak",
        "sev-blocker", "sev-warning", "sev-info", "link", "focus",
    }  # fmt: skip
    assert expected <= set(TOKENS)


@pytest.mark.parametrize("surface", LIGHT_SURFACES)
@pytest.mark.parametrize("text", ["ink", "ink-2", "ink-3"])
def test_text_tiers_on_light_surfaces(text, surface):
    # Tertiary text is used as text throughout (captions, hints), so it meets 4.5 too.
    assert ratio(text, surface) >= TEXT, (text, surface, ratio(text, surface))


@pytest.mark.parametrize("surface", LIGHT_SURFACES)
@pytest.mark.parametrize("text", ["link", "score-strong", "score-adequate", "score-weak"])
def test_score_and_link_colours_as_text_on_light_surfaces(text, surface):
    assert ratio(text, surface) >= TEXT, (text, surface, ratio(text, surface))


@pytest.mark.parametrize("surface", LIGHT_SURFACES)
@pytest.mark.parametrize("text", ["sev-blocker", "sev-warning", "sev-info"])
def test_severity_colours_as_outline_and_label_on_light_surfaces(text, surface):
    # Severity is an outlined tag whose label takes the same colour: text threshold.
    assert ratio(text, surface) >= TEXT, (text, surface, ratio(text, surface))


@pytest.mark.parametrize("fill", ["score-strong", "score-adequate", "score-weak"])
@pytest.mark.parametrize("surface", ["canvas", "card", "sheet"])
def test_score_fills_stand_out_from_the_page(fill, surface):
    assert ratio(fill, surface) >= NON_TEXT


@pytest.mark.parametrize("highlight", ["lime", "highlight-base", "highlight-intense"])
def test_ink_on_lime_and_highlighter(highlight):
    assert ratio("ink", highlight) >= TEXT, (highlight, ratio("ink", highlight))


@pytest.mark.parametrize("text", ["canvas", "card", "sheet", "lime", "soft-green"])
def test_text_on_forest(text):
    assert ratio(text, "forest") >= TEXT, (text, ratio(text, "forest"))


def test_focus_ring_is_visible_on_every_light_surface():
    for surface in LIGHT_SURFACES:
        assert ratio("focus", surface) >= NON_TEXT


def test_score_and_severity_families_are_distinct():
    # A weak score and a blocker must never look alike: the two hues sit apart.
    def hue(token: str) -> float:
        value = TOKENS[token].lstrip("#")
        r, g, b = (int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))
        hi, lo = max(r, g, b), min(r, g, b)
        d = hi - lo
        if hi == r:
            h = ((g - b) / d) % 6
        elif hi == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        return h * 60

    gap = abs(hue("score-weak") - hue("sev-blocker"))
    assert min(gap, 360 - gap) >= 25
