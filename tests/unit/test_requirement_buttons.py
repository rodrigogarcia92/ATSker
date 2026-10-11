"""§12.1 item 5: the requirements are buttons with one detail region (queue U4).

The behaviour is a few lines of script, so the tests read two things: the HTML a reader
gets on load (a button per requirement, none pressed, every detail already in the page)
and the script that toggles `aria-pressed`. The old compact list stays in a `<noscript>`.
"""

import re

from src.i18n import t
from tests.conftest import login
from tests.unit.test_analysis import text_of
from tests.unit.test_report_layout import section, stored

GRADES = [
    {
        "requirement": "python",
        "must_have": True,
        "level": 3,
        "basis": "direct",
        "source": "bullet",
        "bullet_text": "Automaticé los reportes con Python y SQL.",
    },
    {
        "requirement": "snowflake",
        "must_have": True,
        "level": 2,
        "basis": "equivalent",
        "source": "bullet",
        "transfer_reason": "Usas BigQuery, el mismo tipo de almacén.",
        "bullet_text": "Modelé datos en BigQuery.",
    },
    {"requirement": "tableau", "must_have": False, "level": 1, "basis": "none"},
    {"requirement": "dbt", "must_have": False, "level": 0, "basis": "none"},
]

BUTTON = re.compile(
    r'<button type="button" class="req-chip req-(\w+)" aria-pressed="(\w+)"\s+'
    r'aria-controls="req-detail" data-template="(req-tpl-\d+)"[^>]*>\s*'
    r"<span>(.*?)</span>\s*<span class=\"req-level\">(\d)/3</span>",
    re.S,
)


def requirements_page(client, session, career, grades=GRADES):
    application = stored(session, career, grades=grades)
    login(client, career.first.email)
    return section(client.get(f"/applications/{application.id}").text, "requirements")


def test_one_button_per_graded_requirement_none_pressed_on_load(client, session, career):
    page = requirements_page(client, session, career)

    buttons = BUTTON.findall(page)

    assert [name for _band, _pressed, _tpl, name, _level in buttons] == [
        "python",
        "snowflake",
        "tableau",
        "dbt",
    ]
    assert {pressed for _band, pressed, *_ in buttons} == {"false"}, "none is selected on load"
    assert [level for *_, level in buttons] == ["3", "2", "1", "0"], "each shows its L/3"
    assert page.count("<button") == len(GRADES)
    assert 'id="req-detail"' in page and 'aria-live="polite"' in page


def test_every_requirements_detail_is_in_the_page_without_script(client, session, career):
    page = requirements_page(client, session, career)

    templates = re.findall(r'<template id="(req-tpl-\d+)">(.*?)</template>', page, re.S)
    assert len(templates) == len(GRADES), "one detail per button"
    by_id = {name: text_of(body) for name, body in templates}
    python = by_id["req-tpl-0"]
    assert "Imprescindible" in python and "nivel 3 de 3" in python
    assert "directa" in python, "the basis"
    assert "Automaticé los reportes con Python y SQL." in python, "the cited evidence"
    snowflake = by_id["req-tpl-1"]
    assert "Por qué transfiere: Usas BigQuery, el mismo tipo de almacén." in snowflake
    assert "Modelé datos en BigQuery." in snowflake
    assert "Deseable" in by_id["req-tpl-3"] and "Sin cita" in by_id["req-tpl-3"]
    # every button names a template that exists
    assert {tpl for _band, _pressed, tpl, *_ in BUTTON.findall(page)} == set(by_id)


def test_the_old_compact_list_is_the_noscript_fallback(client, session, career):
    page = requirements_page(client, session, career)

    fallback = re.search(r"<noscript>(.*?)</noscript>", page, re.S)

    assert fallback, "without script the list is still there"
    text = text_of(fallback.group(1))
    for grade in GRADES:
        assert grade["requirement"] in text
    assert "Automaticé los reportes con Python y SQL." in text
    assert 'id="req-chips" class="mt-4" hidden' in page, "the buttons wait for the script"


def test_the_summary_counts_match_the_grades(client, session, career):
    page = text_of(requirements_page(client, session, career))

    # covered is level 2 or 3; a gap is level 0 or 1
    assert "4 requisitos: 2 cubiertos, 2 brechas" in page

    one = text_of(requirements_page(client, session, career, GRADES[:1]))
    assert "1 requisito: 1 cubierto, 0 brechas" in one

    gaps = text_of(requirements_page(client, session, career, GRADES[2:3]))
    assert "1 requisito: 0 cubiertos, 1 brecha" in gaps


def test_the_level_decides_the_border_colour_class(client, session, career):
    page = requirements_page(client, session, career)

    bands = {name: band for band, _pressed, _tpl, name, _level in BUTTON.findall(page)}

    assert bands == {
        "python": "strong",
        "snowflake": "adequate",
        "tableau": "weak",
        "dbt": "weak",
    }, "3 strong, 2 adequate, 0 and 1 weak"
    assert len(set(bands.values())) == 3


def test_the_script_toggles_aria_pressed_and_clears_on_a_second_click(client, session, career):
    page = requirements_page(client, session, career)
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)

    assert "getAttribute('aria-pressed') === 'true'" in script, "it reads the pressed state"
    assert "setAttribute('aria-pressed', 'false')" in script, "it unpresses every button"
    assert "setAttribute('aria-pressed', 'true')" in script, "and presses the chosen one"
    assert "detail.textContent = ''" in script, "the region is cleared first"
    assert "if (wasOn) return;" in script, "a second click leaves it cleared"
    assert "localStorage" not in script and "sessionStorage" not in script


def test_a_report_with_no_grades_has_no_buttons(client, session, career):
    page = requirements_page(client, session, career, grades=[])

    assert "<button" not in page
    assert t("report.no_grades", "es") in text_of(page)
