"""Dark mode (PRD §12.6): the theme is the account's own setting, chosen from the menus.

The pages keep nothing in the browser, so the choice lives on the user row and the page
renders in it. The switch sits in the avatar menu and in the phone sheet.
"""

from tests.conftest import login


def test_the_switch_is_in_both_menus_and_the_page_starts_light(client, career):
    login(client, career.first.email)

    page = client.get("/").text

    assert page.count('action="/settings/theme"') == 2, "the avatar menu and the phone sheet"
    assert 'data-theme="light"' in page


def test_dark_is_kept_on_the_account_and_the_page_renders_in_it(client, career):
    login(client, career.first.email)

    answer = client.post(
        "/settings/theme", data={"theme": "dark", "next": "/analyze"}, follow_redirects=False
    )

    assert answer.status_code == 303
    assert answer.headers["location"] == "/analyze", "back to the page the switch was on"
    assert 'data-theme="dark"' in client.get("/analyze").text


def test_an_unknown_theme_is_ignored_and_only_this_site_is_followed(client, career):
    login(client, career.first.email)

    answer = client.post(
        "/settings/theme",
        data={"theme": "blue", "next": "https://example.com"},
        follow_redirects=False,
    )

    assert answer.headers["location"] == "/dashboard"
    assert 'data-theme="light"' in client.get("/").text
