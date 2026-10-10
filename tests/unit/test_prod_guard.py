"""The shared production-database guard (`scripts/_prod_guard.py`), tested on its own.

The fragment is set through the environment, as an operator would, and the fake host below never
names a real endpoint. An empty value stands for "unset": it also overrides a developer's `.env`.
"""

import pytest

from scripts import _prod_guard
from src.config import get_settings

FRAGMENT_VAR = "PROD_DB_HOST_FRAGMENT"
FAKE_FRAGMENT = "ep-prod-fake"
FAKE_PROD_URL = "postgresql://user:pw@ep-prod-fake-0000.example.invalid/atsker"
FAKE_DEV_URL = "postgresql://user:pw@ep-dev-fake-0000.example.invalid/atsker"


@pytest.fixture(autouse=True)
def _fresh_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _set_fragment(monkeypatch, value: str) -> None:
    monkeypatch.setenv(FRAGMENT_VAR, value)
    get_settings.cache_clear()


def test_a_host_containing_the_fragment_is_refused(monkeypatch):
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    assert _prod_guard.refusal_reason(FAKE_PROD_URL, allow_prod=False) is not None


def test_an_unset_fragment_refuses_a_non_local_host(monkeypatch):
    _set_fragment(monkeypatch, "")
    reason = _prod_guard.refusal_reason(FAKE_DEV_URL, allow_prod=False)
    assert reason is not None
    assert FRAGMENT_VAR in reason


def test_an_unset_fragment_allows_a_local_host(monkeypatch):
    _set_fragment(monkeypatch, "")
    for url in (
        "postgresql://user:pw@localhost:5432/atsker",
        "postgresql://user:pw@127.0.0.1/atsker",
        "postgresql://user:pw@[::1]/atsker",
        "postgresql://user:pw@/atsker?host=/var/run/postgresql",
        "sqlite:///local.db",
        "sqlite://",
    ):
        assert _prod_guard.refusal_reason(url, allow_prod=False) is None, url


def test_a_set_fragment_allows_a_different_non_local_host(monkeypatch):
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    assert _prod_guard.refusal_reason(FAKE_DEV_URL, allow_prod=False) is None


def test_the_explicit_opt_in_allows_the_fragment_match(monkeypatch):
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    assert _prod_guard.refusal_reason(FAKE_PROD_URL, allow_prod=True) is None


def test_an_unset_fragment_is_not_switched_off_by_the_opt_in(monkeypatch):
    _set_fragment(monkeypatch, "")
    assert _prod_guard.refusal_reason(FAKE_DEV_URL, allow_prod=True) is not None


def test_messages_never_show_the_host_or_the_fragment(monkeypatch):
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    refused = _prod_guard.refusal_reason(FAKE_PROD_URL, allow_prod=False)
    _set_fragment(monkeypatch, "")
    missing = _prod_guard.refusal_reason(FAKE_DEV_URL, allow_prod=False)
    for message in (refused, missing):
        assert message is not None
        assert "ep-prod-fake" not in message
        assert "ep-dev-fake" not in message
        assert "example.invalid" not in message


def test_a_script_without_an_override_does_not_mention_the_flag(monkeypatch):
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    reason = _prod_guard.refusal_reason(FAKE_PROD_URL, allow_prod=False, override=None)
    assert reason is not None
    assert "--prod" not in reason


def test_an_empty_url_is_left_to_the_callers_own_check(monkeypatch):
    _set_fragment(monkeypatch, "")
    assert _prod_guard.refusal_reason("", allow_prod=False) is None
    assert _prod_guard.refusal_reason("   ", allow_prod=False) is None


def test_a_remote_host_given_in_the_query_string_is_checked(monkeypatch):
    # libpq reads `host` from the query when the authority has none; that host must not look local.
    url = "postgresql://user:pw@/atsker?host=ep-prod-fake-0000.example.invalid"
    _set_fragment(monkeypatch, FAKE_FRAGMENT)
    assert _prod_guard.refusal_reason(url, allow_prod=False) is not None
    _set_fragment(monkeypatch, "")
    assert _prod_guard.refusal_reason(url, allow_prod=False) is not None


def test_a_socket_directory_in_the_query_string_is_local(monkeypatch):
    _set_fragment(monkeypatch, "")
    assert _prod_guard.refusal_reason(
        "postgresql://user:pw@/atsker?host=/var/run/postgresql", allow_prod=False
    ) is None


def test_a_list_with_one_remote_host_is_not_local(monkeypatch):
    _set_fragment(monkeypatch, "")
    url = "postgresql://user:pw@/atsker?host=/var/run/postgresql,ep-dev-fake-0000.example.invalid"
    assert _prod_guard.refusal_reason(url, allow_prod=False) is not None
