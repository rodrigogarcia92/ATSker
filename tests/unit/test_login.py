"""Login behaviour: credentials, the rate limit, and session cookies (PRD F1)."""

from datetime import UTC, datetime, timedelta

from src.auth import sessions
from tests.conftest import PASSWORD, login


def test_valid_credentials_issue_a_session_cookie(client, two_accounts):
    (first, _), _ = two_accounts

    response = client.post(
        "/login",
        data={"email": first.email, "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert sessions.COOKIE_NAME in response.cookies
    assert client.get("/dashboard").status_code == 200


def test_wrong_password_sets_no_cookie(client, two_accounts):
    (first, _), _ = two_accounts

    response = client.post(
        "/login",
        data={"email": first.email, "password": "not the password"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert sessions.COOKIE_NAME not in response.cookies


def test_sixth_attempt_is_refused_even_with_the_right_password(client, two_accounts):
    (first, _), _ = two_accounts
    for _ in range(5):
        client.post("/login", data={"email": first.email, "password": "wrong"})

    response = client.post(
        "/login",
        data={"email": first.email, "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 429
    assert sessions.COOKIE_NAME not in response.cookies


def test_failures_are_counted_per_username(client, two_accounts):
    (first, _), (second, _) = two_accounts
    for _ in range(5):
        client.post("/login", data={"email": first.email, "password": "wrong"})

    response = client.post(
        "/login",
        data={"email": second.email, "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303


def test_logout_clears_the_cookie(client, two_accounts):
    (first, _), _ = two_accounts
    login(client, first.email)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_forged_cookie_is_not_a_session(client, two_accounts):
    (first, _), _ = two_accounts
    client.cookies.set(sessions.COOKIE_NAME, "not-a-signed-token")

    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_expired_session_is_rejected(client, two_accounts):
    (first, _), _ = two_accounts
    token = sessions.issue(first.id, "test-session-secret")

    assert sessions.load(token, "test-session-secret") is not None
    assert sessions.load(token, "test-session-secret", max_age=-1) is None
    assert sessions.load(token, "a-different-secret") is None


def test_renewal_happens_only_after_a_week_of_use():
    now = datetime.now(UTC)
    fresh = now - timedelta(days=1)
    stale = now - timedelta(days=8)

    assert sessions.needs_renewal(fresh.timestamp(), now) is False
    assert sessions.needs_renewal(stale.timestamp(), now) is True
