"""§12.1 item 10: the sticky action rail on a desktop, the bottom bar on a phone (queue U6).

Both carry the same two actions — try a new CV (it opens the attempt modal) and write the
letter — so the tests read the page for exactly one of each in each place, the jump links
in order, the old mid-page block gone, and the script that hides the bar while the modal
is open. An attempt's report is read-only and shows neither.
"""

import re

import pytest

from src.extract import client as extract_client
from src.i18n import t
from src.models import ApplicationAttempt
from tests.conftest import login
from tests.unit.attempt_support import AttemptProvider, analyzed_application, resume_payload
from tests.unit.cv_support import ensure_first_cv
from tests.unit.test_analysis import POSTING, Provider
from tests.unit.test_ingest_routes import DOCX_TYPE, docx_bytes
from tests.unit.test_report_layout import stored

ANCHORS = (
    "#fit",
    "#components",
    "#recruiter",
    "#requirements",
    "#recommendations",
    "#ats",
    "#before",
)


@pytest.fixture(autouse=True)
def _the_first_track_has_a_cv(request):
    """F11.3: an analysis is of a CV, so a test that runs one finds the first track's."""
    ensure_first_cv(request)



@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def full_page(client, career) -> tuple[str, str]:
    """An analysed page with a track, so every section — and every jump link — exists."""
    login(client, career.first.email)
    posted = client.post(
        "/analyze",
        data={"jd_text": POSTING, "track_id": str(career.first_track.id)},
        follow_redirects=False,
    )
    url = posted.headers["location"]
    return url.rsplit("/", 1)[1], client.get(url).text


def part(page: str, tag: str, marker: str) -> str:
    """The `<tag …marker…>…</tag>` element, which is not nested in itself on this page."""
    match = re.search(rf"<{tag}\b[^>]*{marker}[^>]*>.*?</{tag}>", page, re.S)
    assert match, f"the page has its {marker}"
    return match.group(0)


def test_one_opener_in_the_rail_and_one_in_the_phone_bar_for_the_same_modal(
    client, career, provider
):
    _id, page = full_page(client, career)
    rail = part(page, "aside", "aria-label")
    bar = part(page, "div", 'id="action-bar"')

    assert rail.count("data-attempt-open") == 1
    assert bar.count("data-attempt-open") == 1
    assert page.count("data-attempt-open") == 2, "no third opener anywhere"
    assert page.count('<dialog id="attempt-modal"') == 1, "one modal for both"
    assert 'id="attempt-open"' in rail and 'id="attempt-open-bar"' in bar
    assert t("report.actions.try_cv", "es") in rail
    assert t("report.actions.try_cv_short", "es") in bar
    script = page[page.index('document.getElementById("attempt-modal")') :]
    assert 'getElementById("attempt-open")' in script
    assert 'getElementById("attempt-open-bar")' in script
    assert script.count("addEventListener(\"click\", openModal)") == 1, "both share one handler"


def test_both_letter_links_point_to_the_applications_letter(client, career, provider):
    application_id, page = full_page(client, career)
    rail = part(page, "aside", "aria-label")
    bar = part(page, "div", 'id="action-bar"')

    link = f'href="/applications/{application_id}/letter"'
    assert link in rail and link in bar
    assert t("report.actions.letter", "es") in rail
    assert t("report.actions.letter_short", "es") in bar
    assert page.count(link) == 2, "the old bottom link is gone"


def test_the_jump_links_list_the_seven_anchors_in_order(client, career, provider):
    _id, page = full_page(client, career)
    nav = part(page, "nav", 'aria-label="En esta página"')

    assert re.findall(r'href="(#\w+)"', nav) == list(ANCHORS)
    for anchor in ANCHORS:
        assert f'id="{anchor[1:]}"' in page, f"{anchor} lands on a section"


def test_a_report_without_a_recruiter_scan_does_not_link_to_it(client, session, career):
    application = stored(session, career, severity="warning")
    login(client, career.first.email)

    page = client.get(f"/applications/{application.id}").text
    nav = part(page, "nav", 'aria-label="En esta página"')

    anchors = re.findall(r'href="(#\w+)"', nav)
    assert "#recruiter" not in anchors
    # K4: with no track the summary button stays, disabled, in Recomendaciones.
    assert anchors == [
        "#fit",
        "#components",
        "#requirements",
        "#recommendations",
        "#ats",
        "#before",
    ]


def test_the_mid_page_block_and_the_bottom_letter_link_are_gone(client, career, provider):
    _id, page = full_page(client, career)

    assert page.count('id="attempt-open"') == 1, "the button is in the rail only"
    assert "Escribir la carta" not in page
    assert not re.search(r"<h2[^>]*>\s*Carta de presentación", page)
    assert "(.docx)" not in page, "the note that sat under the mid-page button"


def test_the_layout_is_one_760_column_with_the_actions_as_a_row_of_tertiary_buttons(
    client, career, provider
):
    """Design v3: the sticky rail is gone; the three CV actions sit in a row under the header."""
    _id, page = full_page(client, career)
    toolbar = part(page, "aside", "aria-label")

    assert "max-w-[760px]" in page
    assert "lg:sticky" not in page and "lg:flex" not in page
    # The summary opener is a button and its no-script link twin, so four elements, three actions.
    assert toolbar.count("btn btn-tertiary") == 4, "Probar nuevo CV, Carta, Proponer resumen"
    assert "sm:grid-cols-3" in toolbar
    assert "score-number" not in toolbar, "the Job Match is the card below, not a compact copy"


def test_the_phone_bar_is_fixed_safe_area_aware_and_padded_for(client, career, provider):
    _id, page = full_page(client, career)
    bar_tag = re.search(r'<div id="action-bar"[^>]*>', page, re.S).group(0)

    assert "fixed" in bar_tag and "bottom-0" in bar_tag
    assert "md:hidden" in bar_tag, "the bar is a phone control"
    assert "padding-bottom: max(0.75rem, env(safe-area-inset-bottom))" in bar_tag
    assert 'calc(5rem + env(safe-area-inset-bottom))' in page, "the page is padded by the bar"
    assert "viewport-fit=cover" in page, "env() means something on a notched phone"


def test_the_modal_hides_the_bar_while_it_is_open(client, career, provider):
    _id, page = full_page(client, career)
    script = page[page.index('document.getElementById("attempt-modal")') :]

    open_handler = script[script.index("function openModal()") :].split("\n    }\n")[0]
    assert "modal.showModal()" in open_handler
    assert 'bar.classList.add("hidden")' in open_handler
    close_handler = script[script.index('modal.addEventListener("close"') :].split("});")[0]
    assert 'bar.classList.remove("hidden")' in close_handler


def test_every_new_string_exists_in_both_languages():
    for key in (
        "report.actions.try_cv",
        "report.actions.try_cv_short",
        "report.actions.letter",
        "report.actions.letter_short",
        "report.on_this_page",
        "report.actions.label",
    ):
        assert t(key, "es") != key and t(key, "en") != key
    assert t("report.actions.try_cv_short", "es") == "Probar nuevo CV"
    assert t("report.actions.try_cv_short", "en") == "Try a new CV"
    assert t("report.actions.letter_short", "es") == "Escribir carta"
    assert t("report.on_this_page", "es") == "En esta página"


def test_the_attempt_view_has_no_rail_and_no_bar(
    client, session, career, monkeypatch, test_settings
):
    stub = AttemptProvider(
        bullet_id=str(career.first_bullet.id),
        resume=resume_payload(career.first_bullet.text_es),
    )
    monkeypatch.setattr(extract_client, "_post", stub)
    login(client, career.first.email)
    application, _analysis = analyzed_application(session, career, stub)
    client.post(
        f"/applications/{application.id}/attempts",
        files={
            "file": ("cv.docx", docx_bytes("Experiencia", career.first_bullet.text_es), DOCX_TYPE)
        },
        follow_redirects=False,
    )
    attempt = session.query(ApplicationAttempt).one()

    raw = client.get(f"/applications/{application.id}/attempts/{attempt.id}/report").text

    assert 'aria-label="Acciones"' not in raw, "the shell's own <aside> is not the actions rail"
    assert 'id="action-bar"' not in raw
    assert "data-attempt-open" not in raw
    assert "max-w-[760px]" in raw, "the column is the same; only the actions are gone"
