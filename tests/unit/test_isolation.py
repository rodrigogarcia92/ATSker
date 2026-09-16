"""Profile isolation between the two users (PRD F1).

The requirement is that user A gets 404 — not 403 — for user B's records by id, so
that the response says nothing about whether the id exists.
"""

from tests.conftest import login


def test_own_profile_is_reachable_and_another_users_is_not(client, two_accounts):
    (first, first_profile), (second, second_profile) = two_accounts
    login(client, first.email)

    assert client.get(f"/profile/{first_profile.id}").status_code == 200
    assert client.get(f"/profile/{second_profile.id}").status_code == 404


def test_unknown_and_malformed_profile_ids_are_404(client, two_accounts):
    (first, _), _ = two_accounts
    login(client, first.email)

    assert client.get("/profile/2f0c1c1e-0000-4000-8000-000000000000").status_code == 404
    assert client.get("/profile/not-a-uuid").status_code == 404


def test_anonymous_request_is_redirected_to_login(client, two_accounts):
    (_, first_profile), _ = two_accounts

    response = client.get(f"/profile/{first_profile.id}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
