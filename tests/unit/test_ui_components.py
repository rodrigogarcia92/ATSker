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


def test_each_band_renders_its_word_and_its_colour_class_together():
    """Design v3 §4 (amended 2026-10-12): the number, the band word and the filled segments
    take the band's colour — Fuerte forest, Adecuado ochre, Débil brick — and the band word
    still says the band."""
    for value, band, word in (
        (0.9, "strong", "Fuerte"),
        (0.6, "adequate", "Adecuado"),
        (0.2, "weak", "Débil"),
    ):
        html = render_macro(f'{{{{ ui.score({value}, "Skills", "") }}}}')

        assert f'data-band="{band}"' in html, f"{value} carries the {band} band"
        assert f'<span class="score-band">{word}</span>' in html, "the band word is there"
        assert f'class="score-segment band-{band}' in html, "the segments carry the band"


def test_a_bare_score_number_takes_its_band_colour():
    """Design v3 §4: a score outside the Score component — the history's *Ajuste* column, an
    attempt's sub-score line — carries the same three band colours."""
    for value, band in ((86, "strong"), (63, "adequate"), (40, "weak")):
        html = render_macro(f"{{{{ ui.band_number({value}) }}}}")

        assert f'<span class="band-number-{band}">{value}</span>' in html


def test_a_sub_score_renders_its_own_progress_bar():
    """Design v3 §4: a sub-score's progress bar fills in its band colour on a vellum track;
    the number above it is the value, so the bar is decorative."""
    html = render_macro('{{ ui.score(0.63, "Experiencia", "", false, false, true) }}')

    assert 'class="score-bar" aria-hidden="true"' in html
    assert '<span style="width: 63%"></span>' in html
    assert 'data-band="adequate"' in html, "the bar takes the sub-score's own band"
    assert "score-segments" not in html, "a sub-score has the bar, not the five-segment row"


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



def test_the_top_bar_links_are_plain_text_with_no_icon(client, career):
    """Design v3 §5: the bar is words only; the accessible name is the visible label."""
    login(client, career.first.email)
    page = client.get("/dashboard").text
    bar = page[page.index('class="topnav"') : page.index("</nav>", page.index('class="topnav"'))]

    assert "<svg" not in bar
    assert re.search(r'<a href="/analyze" class="nav-link[^"]*"[^>]*>Analizar</a>', bar)
    assert re.search(r'<a href="/tracks" class="nav-link[^"]*"[^>]*>Líneas de carrera</a>', bar)
