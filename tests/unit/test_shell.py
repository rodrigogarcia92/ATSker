"""§12.1's shell: the rail, its three groups and nine links, and the renamed wording.

The rail is the second user's map of the application, so the links are asserted by
href, not by styling: a link that disappears behind an icon is still a link, and one
that is not in the HTML is not reachable at all.
"""

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


def test_vocabulario_is_reachable_from_perfil(client, career):
    login(client, career.first.email)

    page = client.get("/profile").text

    assert 'href="/vocabulary"' in page, "Perfil is where Vocabulario lives now"


def test_the_login_page_has_no_rail(client):
    page = client.get("/login").text

    assert 'id="rail-body"' not in page
    assert ">Postular<" not in page
