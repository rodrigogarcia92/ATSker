"""§12.1's shell: the rail, its three groups and nine links, and the renamed wording.

The rail is the second user's map of the application, so the links are asserted by
href, not by styling: a link that disappears behind an icon is still a link, and one
that is not in the HTML is not reachable at all.
"""

import pytest

from src.web.recall import query_rows
from tests.conftest import login

# The nine destinations §12.1 groups under Postular, Tu material and Cuenta.
NAV_LINKS = (
    "/dashboard",
    "/analyze",
    "/applications",
    "/import",
    "/tracks",
    "/roles",
    "/stories",
    "/letters",
    "/profile",
)

# Every page a signed-in user can reach from the rail, for the wording sweep.
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


def test_the_rail_groups_and_all_nine_links_render_for_a_signed_in_user(client, career):
    login(client, career.first.email)

    page = client.get("/dashboard").text

    for group in ("Postular", "Tu material", "Cuenta"):
        assert group in page, f"the {group} group is part of the rail"
    for href in NAV_LINKS:
        assert f'href="{href}"' in page, f"{href} is a rail destination"
    assert 'id="rail-body"' in page and 'id="rail-toggle"' in page
    assert "/vocabulary" not in page, "Vocabulario left the rail"


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
    assert 'id="rail-body"' in response.text, f"the shell reached {url}"


def test_the_content_column_can_shrink_and_wide_tables_scroll(client, career):
    """N6.6: a wide table must scroll inside its own box, not stretch the page — which
    only works if the flex child holding it is allowed to shrink."""
    login(client, career.first.email)

    page = client.get("/dashboard").text

    assert '<main class="main min-w-0">' in page
    assert 'class="mx-auto w-full min-w-0' in page


def test_vocabulario_is_reachable_from_perfil(client, career):
    login(client, career.first.email)

    page = client.get("/profile").text

    assert 'href="/vocabulary"' in page, "Perfil is where Vocabulario lives now"


def test_the_login_page_has_no_rail(client):
    page = client.get("/login").text

    assert 'id="rail-body"' not in page
    assert ">Postular<" not in page


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
