"""§12.8's landing: the page at `/` for visitors with no session.

The copy is the approved mockup's (`private_docs/design/v3/Landing.dc.html`), so these
tests hold the page's shape and its switches, not the wording of every line: the eight
sections in the PRD's order, the demo button behind its setting, the language link, and
the reveal that must never hide the page on its own.
"""

from pathlib import Path

from src.config import Settings, get_settings
from src.i18n import t
from src.i18n.strings import STRINGS
from tests.conftest import login

ROOT = Path(__file__).resolve().parents[2]
SRC_CSS = ROOT / "src" / "web" / "static" / "src.css"
REPOSITORY = "https://github.com/rodrigogarcia92/ATSker"

# §12.8's eight sections, in order, each by a phrase only that section carries.
SECTIONS = (
    "Tú controlas tu CV. ATSker te ayuda a afinarlo para cada oferta.",
    "Antes de postular, conoce tus brechas",
    "¿El ATS puede leer tu CV?",
    "Importa una vez",
    "Con IA, honesto por diseño",
    "Cómo funciona",
    "Privacidad, en palabras simples",
    "proyecto de portafolio",
)

FEATURE_CARDS = (
    "landing.what.import.title",
    "landing.what.tracks.title",
    "landing.what.report.title",
    "landing.what.ceiling.title",
    "landing.what.writing.title",
)


def test_a_visitor_without_a_session_gets_the_landing(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Tú controlas tu CV" in response.text


def test_the_landing_is_not_behind_the_shell(client):
    """The rail belongs to the signed-in pages; the landing carries its own header."""
    page = client.get("/").text

    assert 'id="rail-body"' not in page
    assert ">Postular<" not in page


def test_a_signed_in_visitor_is_still_sent_to_the_dashboard(client, career):
    login(client, career.first.email)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_the_eight_sections_are_all_there_in_the_prds_order(client):
    """Each phrase is looked for after the one before it, so a repeated label (the nav
    links "Cómo funciona" before its section does) cannot stand in for the section."""
    page = client.get("/").text

    cursor = 0
    for phrase in SECTIONS:
        found = page.find(phrase, cursor)
        assert found >= 0, f"missing or out of order: {phrase}"
        cursor = found + len(phrase)


def test_the_five_feature_cards_are_all_there(client):
    page = client.get("/").text

    for key in FEATURE_CARDS:
        assert t(key, "es") in page, key


def test_the_static_preview_card_says_it_is_sample_data(client):
    """§12.8: no product image until N8.18 — the card is live HTML with sample figures."""
    page = client.get("/").text

    assert "<img" not in page
    assert t("landing.preview.sample", "es") in page


def test_the_page_links_the_repository(client):
    page = client.get("/").text

    assert page.count(REPOSITORY) >= 3, "the strip, the hero and the footer"


def test_the_language_link_switches_the_page_to_english(client):
    page = client.get("/?lang=en").text

    assert "You control your CV" in page
    assert "Tú controlas tu CV" not in page
    assert 'href="/?lang=es"' in page


def test_an_unknown_language_falls_back_to_the_default(client):
    page = client.get("/?lang=de").text

    assert "Tú controlas tu CV" in page


def test_the_demo_setting_defaults_to_off():
    assert Settings.model_fields["demo_enabled"].default is False


def test_the_demo_button_is_hidden_by_default(client):
    page = client.get("/").text

    assert t("landing.demo", "es") not in page
    assert 'href="/demo"' not in page


def test_the_demo_button_appears_when_the_setting_turns_it_on(client, monkeypatch):
    monkeypatch.setenv("DEMO_ENABLED", "true")
    get_settings.cache_clear()

    page = client.get("/").text

    assert t("landing.demo", "es") in page
    assert 'href="/demo"' in page


def test_every_landing_string_has_both_languages():
    entries = {key: value for key, value in STRINGS.items() if key.startswith("landing.")}

    assert entries, "the landing's copy is one block in the strings dict"
    assert sorted(key for key, value in entries.items() if set(value) != {"es", "en"}) == []


def test_the_landing_block_sits_right_after_the_app_tagline():
    """The lane rule: the block is one contiguous run directly after `app.tagline`."""
    keys = list(STRINGS)
    landing = [index for index, key in enumerate(keys) if key.startswith("landing.")]

    assert landing == list(range(landing[0], landing[-1] + 1))
    assert keys[landing[0] - 1] == "app.tagline"


def _media_block(css: str, query: str) -> str:
    """The whole `@media (query) { … }` text, nested braces included."""
    start = css.index(f"@media ({query})")
    depth = 0
    for index in range(css.index("{", start), len(css)):
        if css[index] == "{":
            depth += 1
        elif css[index] == "}":
            depth -= 1
            if depth == 0:
                return css[start : index + 1]
    raise AssertionError(f"unbalanced {query}")


def test_the_reveal_moves_only_under_prefers_reduced_motion_no_preference():
    """§12.8: fully visible without JavaScript, and none under reduced motion.

    The hidden state is keyed on the class the script adds, and every reveal rule — both the
    scroll-driven path and the observer path — lives inside the `no-preference` block, so a
    browser asking for reduced motion, or one running no script at all, shows the page.
    """
    css = SRC_CSS.read_text(encoding="utf-8")
    block = _media_block(css, "prefers-reduced-motion: no-preference")

    assert "animation-timeline: view()" in block, "the CSS path where it is supported"
    assert ".reveal-js .reveal {" in block, "the fallback keys on the class the script adds"
    assert ".reveal" not in css.replace(block, ""), "nothing hides a section outside it"


def test_the_landing_script_is_the_fallback_and_needs_no_library(client):
    page = client.get("/").text

    assert "IntersectionObserver" in page
    assert "reveal-js" in page
    assert "<script src=" not in page, "no library and no third-party script"
    assert 'class="reveal' in page, "the sections it reveals"
