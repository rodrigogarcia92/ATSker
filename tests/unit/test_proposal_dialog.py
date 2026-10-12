"""§12.5: the one dialog behind both proposal pop-ups (queue K3).

The macro is the markup, the script in `base.html` is the behaviour, and the F10 attempt
modal is left exactly as it was — it shares only the sheet's CSS. The tests read the macro's
roles and labels in both languages, the opener's two forms (button with script, link
without), and the script's contract with the markup.
"""

import re
from pathlib import Path

from src.web.templating import _TEMPLATES
from tests.conftest import login

WEB = Path(__file__).parents[2] / "src" / "web"


def render_macro(source: str, lang: str = "es") -> str:
    template = _TEMPLATES.env.from_string('{% import "_ui.html" as ui with context %}' + source)
    return template.render(lang=lang)


def test_the_dialog_is_a_labelled_modal_with_a_close_button_in_both_languages():
    for lang, close in (("es", "Cerrar"), ("en", "Close")):
        html = render_macro('{{ ui.dialog("proposal-dialog") }}', lang)

        assert html.startswith('<dialog id="proposal-dialog"')
        assert 'role="dialog"' in html and 'aria-modal="true"' in html
        assert 'aria-labelledby="proposal-dialog-title"' in html
        assert 'id="proposal-dialog-title"' in html, "the label points at a real heading"
        button = re.search(r"<button[^>]*data-dialog-close[^>]*>(.*?)</button>", html, re.S)
        assert button and button.group(1).strip() == close
        assert f'aria-label="{close}"' in button.group(0)
        assert 'type="button"' in button.group(0), "closing never submits anything"


def test_the_dialog_has_a_body_for_the_partial_and_a_line_for_a_failed_load():
    html = render_macro('{{ ui.dialog("proposal-dialog") }}')

    assert re.search(r'<div[^>]*data-dialog-body[^>]*tabindex="-1"', html), "focusable body"
    assert re.search(r'<p role="alert" hidden data-dialog-error', html)
    assert 'data-loading="Cargando…"' in html
    assert "propuesta sin aceptar" in html, "the close-over-a-proposal question is carried"
    english = render_macro('{{ ui.dialog("proposal-dialog") }}', "en")
    assert 'data-loading="Loading…"' in english
    assert "has not been accepted" in english


def test_an_opener_is_a_button_with_a_url_and_a_link_without_script():
    html = render_macro(
        '{{ ui.dialog_opener("/applications/1/summary?dialog=1", "/applications/1/summary",'
        ' "Proponer resumen", "tag-class") }}'
    )

    button = re.search(r"<button[^>]*data-dialog-url[^>]*>(.*?)</button>", html, re.S)
    assert button and 'type="button"' in button.group(0) and " hidden " in button.group(0)
    assert 'data-dialog-url="/applications/1/summary?dialog=1"' in button.group(0)
    assert 'data-dialog-title="Proponer resumen"' in button.group(0)
    link = re.search(r'<a href="([^"]*)"[^>]*data-dialog-fallback[^>]*>(.*?)</a>', html, re.S)
    assert link and link.group(1) == "/applications/1/summary"
    assert link.group(2) == "Proponer resumen"
    assert html.count("tag-class") == 2, "both carry the caller's classes"


def test_the_shared_script_serves_the_markup_it_is_given(client, career):
    login(client, career.first.email)

    page = client.get("/dashboard").text

    script = page[page.index("§12.5: the shared proposal dialog") :]
    for hook in (
        "dialog[data-proposal-dialog]",
        "[data-dialog-opener]",
        "[data-dialog-fallback]",
        "[data-dialog-url]",
        "[data-dialog-body]",
        "data-dialog-form",
        "data-dialog-dirty",
        "[data-progress-status]",
        "[data-progress-timer]",
    ):
        assert hook in script, hook
    assert "showModal()" in script and "opener.focus()" in script, "focus returns to the opener"
    assert "window.confirm(dialog.dataset.confirm)" in script
    assert "method: 'POST'" in script, "a form is posted; opening is a GET"
    assert "cancel" in script, "Escape goes through the same confirmation"


def test_the_sheet_is_centred_and_full_screen_on_a_phone_and_f10_css_is_untouched():
    built = (WEB / "static" / "app.css").read_text(encoding="utf-8")

    desktop = re.search(r"\.dialog-sheet\{[^}]*\}", built).group(0)
    assert "margin:auto" in desktop
    phone = re.search(r"@media \(max-width:640px\)\{\.dialog-sheet\{[^}]*\}", built).group(0)
    assert "max-width:none" in phone and "max-height:none" in phone and "inset:0" in phone
    assert re.search(r"\.attempt-modal\{[^}]*\}", built), "the F10 rule is its own, as before"


def test_the_f10_modal_keeps_its_own_markup_and_script():
    # §12.7: the modal is now one partial both layouts include, so the two cannot drift.
    report = (WEB / "templates" / "analyze" / "report.html").read_text(encoding="utf-8")
    modal = (WEB / "templates" / "analyze" / "_attempt_modal.html").read_text(encoding="utf-8")

    assert "analyze/_attempt_modal.html" in report, "the single column still includes it"
    assert '<dialog id="attempt-modal" class="attempt-modal"' in modal
    assert "dialog-sheet" not in modal, "K3 does not rebuild the F10 modal"
