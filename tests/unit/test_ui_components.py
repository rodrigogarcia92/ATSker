"""§12.1's score and severity components (`_ui.html`).

The band thresholds are presentation, so they are tested where they live: the macro.
A score is always an integer out of 100, the five-segment row is how a score reads
without colour, and a severity tag is an outlined icon and word — never a fill.
"""

import re

from src.web.templating import _TEMPLATES
from tests.conftest import login


def render_macro(source: str) -> str:
    template = _TEMPLATES.env.from_string(
        '{% import "_ui.html" as ui with context %}' + source
    )
    return template.render(lang="es")


def test_the_score_band_boundaries_are_75_and_50():
    cases = (
        (0.75, "strong"),
        (0.88, "strong"),
        (0.74, "adequate"),
        (0.50, "adequate"),
        (0.49, "weak"),
        (0.0, "weak"),
    )
    for value, band in cases:
        html = render_macro(f'{{{{ ui.score({value}, "Skills", "") }}}}')
        assert f'data-band="{band}"' in html, f"{value} is {band}"


def test_every_score_renders_as_an_integer_out_of_100():
    halves = render_macro('{{ ui.score(0.5, "Skills", "") }}')
    thirds = render_macro('{{ ui.score(0.333, "Skills", "") }}')

    assert ">50</span>" in halves and "50." not in halves, "0.5 is 50, not 0.5"
    assert ">33</span>" in thirds, "0.333 is 33, never 33.3"


def test_a_score_carries_five_segments_one_per_twenty_points():
    html = render_macro('{{ ui.score(0.5, "Skills", "") }}')

    assert html.count('class="score-segment band-') == 5
    assert html.count("is-on") == 2, "50 points fills the 20 and 40 segments, not the 60"


def test_a_score_is_never_colour_alone():
    html = render_macro('{{ ui.score(0.9, "Skills", "") }}')

    assert "Fuerte" in html, "the band word is beside the number and the segments"


def test_severity_is_an_icon_and_a_word_and_never_a_fill():
    for level in ("blocker", "warning", "info"):
        html = render_macro(f'{{{{ ui.severity("{level}", "Etiqueta") }}}}')

        assert f"sev-{level}" in html and "<svg" in html and "Etiqueta" in html
        assert " bg-" not in html, "severity is outlined, never filled"
        assert "background" not in html


def test_level_bars_fill_to_the_level_and_write_the_number():
    two = render_macro("{{ ui.level_bars(2) }}")
    zero = render_macro("{{ ui.level_bars(0) }}")

    assert two.count('class="level-bar band-') == 3
    assert two.count("is-on") == 2
    assert ">2</span>" in two
    assert zero.count("is-on") == 0


def _analyze_rail_link(client, career) -> str:
    login(client, career.first.email)
    page = client.get("/dashboard").text
    match = re.search(r'<a href="/analyze"[^>]*>.*?</a>', page, re.S)
    assert match, "the rail links to /analyze"
    return match.group(0)


def test_the_analizar_icon_is_a_document_with_three_score_bars(client, career):
    link = _analyze_rail_link(client, career)
    icon = re.search(r"<svg.*?</svg>", link, re.S).group(0)
    paths = re.findall(r'<path d="([^"]+)"', icon)

    assert "<circle" not in icon, "the magnifier lens is gone"
    assert [d for d in paths if d.startswith("M6 3")], "a page outline"
    assert [d for d in paths if d.startswith("M14 3")], "its folded corner"
    bars = [d for d in paths if d.startswith("M9 ")]
    assert len(bars) == 3, "three score bars"
    lengths = [float(re.search(r"h([\d.]+)$", d).group(1)) for d in bars]
    assert lengths == sorted(lengths, reverse=True), "of decreasing length"
    assert len(set(lengths)) == 3


def test_the_analizar_link_keeps_its_label_and_a_hidden_icon(client, career):
    link = _analyze_rail_link(client, career)

    assert 'aria-hidden="true"' in link, "the icon is decoration"
    assert 'aria-label="Analizar"' in link, "nav.analyze is the accessible name"


# --- V3: Puestos objetivo is a branch, Historias a quill (PRD §12.1) ---


def _rail_link(client, career, href: str) -> str:
    login(client, career.first.email)
    page = client.get("/dashboard").text
    match = re.search(rf'<a href="{href}"[^>]*>.*?</a>', page, re.S)
    assert match, f"the rail links to {href}"
    return match.group(0)


def test_the_tracks_icon_is_a_branch_not_concentric_circles(client, career):
    link = _rail_link(client, career, "/tracks")
    icon = re.search(r"<svg.*?</svg>", link, re.S).group(0)

    centres = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)"', icon)
    assert len(centres) == len(set(centres)), "no two circles share a centre"
    assert len(centres) >= 2, "paths end in small nodes"
    stems = re.findall(r'<path d="(M12 21[^"]*)"', icon)
    assert stems, "one stem rises from the bottom"
    assert len(re.findall(r'<path d="M12 15', icon)) >= 2, "and splits into separate paths"


def test_the_stories_icon_is_a_quill_not_the_book(client, career):
    link = _rail_link(client, career, "/stories")
    icon = re.search(r"<svg.*?</svg>", link, re.S).group(0)
    paths = re.findall(r'<path d="([^"]+)"', icon)

    assert "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" not in paths, "the book is gone"
    assert len(paths) >= 2, "a feather and its shaft"
    assert any(re.fullmatch(r"M[\d.]+ [\d.]+ [\d.]+ [\d.]+", d) for d in paths), "the shaft"


def test_the_new_icons_stay_decoration_and_the_links_keep_their_labels(client, career):
    tracks = _rail_link(client, career, "/tracks")
    stories = _rail_link(client, career, "/stories")

    for link in (tracks, stories):
        assert 'aria-hidden="true"' in link
    assert 'aria-label="Puestos objetivo"' in tracks
    assert 'aria-label="Historias"' in stories
