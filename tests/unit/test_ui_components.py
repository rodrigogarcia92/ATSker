"""§12.1's score and severity components (`_ui.html`).

The band thresholds are presentation, so they are tested where they live: the macro.
A score is always an integer out of 100, the five-segment row is how a score reads
without colour, and a severity tag is an outlined icon and word — never a fill.
"""

from src.web.templating import _TEMPLATES


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
