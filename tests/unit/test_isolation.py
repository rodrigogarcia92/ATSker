"""Profile isolation between the two users (PRD F1).

The requirement is that user A gets 404 — not 403 — for user B's records by id, so
that the response says nothing about whether the id exists. The profile itself is
addressed as `/profile` without an id, so the records under test are the career
rows: roles, bullets, stories and letter templates.
"""

from tests.conftest import login


def test_another_users_records_are_404_and_own_records_are_200(client, career):
    login(client, career.first.email)

    assert client.get(f"/roles/{career.first_role.id}").status_code == 200
    assert client.get(f"/roles/{career.second_role.id}").status_code == 404
    assert client.get(f"/bullets/{career.first_bullet.id}/edit").status_code == 200
    assert client.get(f"/bullets/{career.second_bullet.id}/edit").status_code == 404
    assert client.get(f"/stories/{career.first_story.id}").status_code == 200
    assert client.get(f"/stories/{career.second_story.id}").status_code == 404
    assert client.get(f"/letters/{career.first_letter.id}/edit").status_code == 200
    assert client.get(f"/letters/{career.second_letter.id}/edit").status_code == 404


def test_writes_against_another_users_records_are_refused(client, career):
    login(client, career.first.email)

    update = client.post(
        f"/stories/{career.second_story.id}",
        data={"title": "Robada", "body": "no debería guardarse"},
        follow_redirects=False,
    )
    delete = client.post(f"/stories/{career.second_story.id}/delete", follow_redirects=False)
    toggle = client.post(
        f"/bullets/{career.second_bullet.id}/active", data={}, follow_redirects=False
    )

    assert update.status_code == 404
    assert delete.status_code == 404
    assert toggle.status_code == 404


def test_unknown_and_malformed_ids_are_404(client, career):
    login(client, career.first.email)

    assert client.get("/roles/2f0c1c1e-0000-4000-8000-000000000000").status_code == 404
    assert client.get("/roles/not-a-uuid").status_code == 404
    assert client.get("/stories/not-a-uuid").status_code == 404


def test_anonymous_request_is_redirected_to_login(client, career):
    response = client.get(f"/roles/{career.first_role.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_profile_page_shows_only_the_signed_in_user(client, career):
    login(client, career.first.email)

    page = client.get("/profile").text

    assert "Ana" in page
    assert "Bea" not in page
