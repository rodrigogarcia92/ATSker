"""Design v3 §5's shell: the top bar, its links, the avatar menu and the phone sheet.

The bar is the second user's map of the application, so the links are asserted by href,
not by styling: a link that is not in the HTML is not reachable at all.
"""

import re

import pytest

from src.i18n.strings import STRINGS
from src.web.recall import query_rows
from tests.conftest import login

# The eight destinations in the bar's centre; Perfil and Vocabulario live in the avatar menu.
NAV_LINKS = (
    "/dashboard",
    "/analyze",
    "/applications",
    "/import",
    "/tracks",
    "/roles",
    "/stories",
    "/letters",
)
MENU_LINKS = ("/profile", "/vocabulary")

# Every page a signed-in user can reach from the bar, for the wording sweep.
SIGNED_IN_PAGES = (
    "/dashboard",
    "/analyze",
    "/applications",
    "/import",
    "/tracks",
    "/roles",
    "/stories",
    "/letters",
    "/profile",
    "/vocabulary",
)


def test_the_top_bar_has_the_main_links_and_the_avatar_menu_has_the_account_ones(client, career):
    login(client, career.first.email)

    page = client.get("/dashboard").text

    assert '<header class="topbar">' in page and 'class="topnav"' in page
    assert "atsker" in page, "the wordmark"
    for href in NAV_LINKS + MENU_LINKS:
        assert f'href="{href}"' in page, f"{href} is reachable from the bar"
    for gone in ("rail-body", "rail-toggle", "Postular", "Tu material"):
        assert gone not in page, f"{gone} left with the rail"
    assert 'action="/logout"' in page and 'action="/settings/lang"' in page


def test_the_avatar_menu_and_the_phone_sheet_are_details_that_work_without_script(client, career):
    login(client, career.first.email)

    page = client.get("/dashboard").text

    assert page.count("<details class=\"menu ") == 2, "one avatar menu, one phone sheet"
    assert 'class="sheet" role="dialog"' in page
    sheet = page[page.index('class="sheet"') :]
    for href in NAV_LINKS + MENU_LINKS:
        assert f'href="{href}"' in sheet, f"the sheet keeps {href}"
    assert 'name="lang" value="en"' in sheet and 'action="/logout"' in sheet


def test_the_current_page_is_marked_in_the_bar(client, career):
    login(client, career.first.email)

    page = client.get("/analyze").text

    assert re.search(r'<a href="/analyze" class="nav-link "[^>]* aria-current="page"', page)
    assert not re.search(r'<a href="/tracks" class="nav-link "[^>]* aria-current="page"', page)


def test_trayectoria_appears_nowhere_in_the_rendered_spanish_pages(client, career):
    login(client, career.first.email)

    for path in SIGNED_IN_PAGES:
        response = client.get(path)
        assert response.status_code == 200, path
        assert "Trayectoria" not in response.text, f"the rename reached {path}"


SCREEN_PATHS = (
    "/dashboard",
    "/analyze",
    "/applications",
    "/import",
    "/tracks",
    "/tracks/new",
    "/tracks/{track}",
    "/tracks/{track}/bullets",
    "/tracks/{track}/edit",
    "/tracks/{track}/letter",
    "/tracks/{track}/delete",
    "/roles",
    "/roles/new",
    "/roles/{role}",
    "/roles/{role}/edit",
    "/roles/{role}/delete",
    "/roles/{role}/bullets/new",
    "/stories",
    "/stories/new",
    "/stories/{story}",
    "/stories/{story}/delete",
    "/letters",
    "/letters/{letter}/edit",
    "/letters/{letter}/delete",
    "/summaries/{summary}",
    "/summaries/{summary}/delete",
    "/bullets/{bullet}/edit",
    "/bullets/{bullet}/delete",
    "/profile",
    "/profile/delete",
    "/vocabulary",
)


@pytest.mark.parametrize("path", SCREEN_PATHS)
def test_every_signed_in_screen_renders_with_the_shell(client, career, path):
    """N6.4: no screen 500s on a template error after the tokens were applied."""
    login(client, career.first.email)
    url = path.format(
        track=career.first_track.id,
        role=career.first_role.id,
        story=career.first_story.id,
        letter=career.first_letter.id,
        summary=career.first_summary.id,
        bullet=career.first_bullet.id,
    )

    response = client.get(url)

    assert response.status_code == 200, url
    assert 'class="topbar"' in response.text, f"the shell reached {url}"


def test_the_content_column_can_shrink_and_wide_tables_scroll(client, career):
    """N6.6: a wide table must scroll inside its own box, not stretch the page — which
    only works if the flex child holding it is allowed to shrink."""
    login(client, career.first.email)

    page = client.get("/dashboard").text

    assert '<main class="main min-w-0">' in page
    assert 'class="mx-auto w-full min-w-0' in page


def test_vocabulario_is_reachable_from_perfil_and_from_the_avatar_menu(client, career):
    login(client, career.first.email)

    page = client.get("/profile").text

    assert page.count('href="/vocabulary"') >= 3, "the profile text, the avatar menu and the sheet"


def test_the_login_page_has_no_top_bar(client):
    page = client.get("/login").text

    assert 'class="topbar"' not in page
    assert 'class="sheet"' not in page


def test_recall_labels_are_shown_in_the_readers_language():
    """N6.6: the derivation answers in its own English words; the panel does not print
    them at a Spanish reader, and never hides a label it does not recognise."""
    payload = {
        "queries": [
            {"label": "broad", "passed": True},
            {"label": "core", "passed": True},
            {"label": "strict", "passed": False},
            {"label": "invented", "passed": True},
        ]
    }

    assert [row["label"] for row in query_rows(payload, "es")] == [
        "amplia",
        "núcleo",
        "estricta",
        "invented",
    ]
    assert [row["label"] for row in query_rows(payload, "en")] == [
        "broad",
        "core",
        "strict",
        "invented",
    ]


def test_no_spanish_string_says_encaje():
    """§12.1 (queue L7): the score's word is "Ajuste" everywhere it is shown."""
    offenders = [key for key, entry in STRINGS.items() if "ncaje" in entry.get("es", "")]

    assert offenders == []


def test_the_score_is_ajuste_in_spanish_and_fit_in_english():
    assert STRINGS["applications.score"] == {"es": "Ajuste", "en": "Fit"}
    assert STRINGS["attempt.score"]["es"] == "Ajuste {score} · techo {ceiling}"
    assert STRINGS["attempt.score"]["en"] == "Fit {score} · ceiling {ceiling}"
    assert STRINGS["attempt.ready.match_band"]["es"].startswith("El ajuste (")
    assert STRINGS["attempt.ready.match_target"]["en"].startswith("The fit (")
    assert STRINGS["report.sub.semantic"]["es"] == "Ajuste semántico"
    assert STRINGS["report.sub_caption.semantic"]["es"].startswith("Ajuste semántico")
    assert STRINGS["report.sub_caption.semantic"]["en"].startswith("Semantic fit")
    assert STRINGS["app.tagline"]["es"].endswith("de ajuste entre tu currículum y una oferta")

