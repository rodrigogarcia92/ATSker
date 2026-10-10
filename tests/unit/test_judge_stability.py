"""The judge-stability measurement script (PRD §9, F10.4, A3).

A fake provider proves the parts the operator must be able to trust before spending
money: the production host is refused without `--prod`, confirmation is required, and
each repeat bypasses the content-hash cache (a cached re-run would measure the cache,
not the judge). The band itself is data — a provisional constant — until the operator
runs the script on real analyses.
"""

import pytest

from scripts import judge_stability
from src.applications import create_application
from src.config import get_settings
from src.extract import client as extract_client
from src.score.weights import STABILITY_BAND
from tests.conftest import TEST_MODEL
from tests.unit.test_analysis import POSTING, Provider

FRAGMENT_VAR = "PROD_DB_HOST_FRAGMENT"
FAKE_FRAGMENT = "ep-prod-fake"
PROD_URL = "postgresql://user:pw@ep-prod-fake-0000.example.invalid/atsker"
DEV_URL = "postgresql://user:pw@ep-example-100.us-east-1.aws.neon.tech/atsker"


@pytest.fixture(autouse=True)
def production_fragment(monkeypatch):
    """The fragment is set for every test here; the unset cases override it with an empty value."""
    monkeypatch.setenv(FRAGMENT_VAR, FAKE_FRAGMENT)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def provider(monkeypatch, test_settings, career) -> Provider:
    stub = Provider(str(career.first_bullet.id))
    monkeypatch.setattr(extract_client, "_post", stub)
    return stub


def _stored(session, career, provider):
    from src.analysis import analyze

    analysis = analyze(
        career.first_profile.id, session, jd_text=POSTING, track=career.first_track
    )
    application = create_application(
        career.first_profile.id,
        session,
        jd_text=POSTING,
        jd_hash=analysis.jd_hash,
        report=analysis.report,
        weights_version=analysis.weights_version,
        prompt_versions=analysis.prompt_versions,
        token_cost_usd=analysis.cost_usd,
        track_id=career.first_track.id,
    )
    session.commit()
    return application


def test_the_prod_host_is_refused_without_the_flag():
    with pytest.raises(SystemExit):
        judge_stability.check_target(PROD_URL, allow_prod=False)
    # Deliberate opt-in passes.
    judge_stability.check_target(PROD_URL, allow_prod=True)


def test_the_dev_host_is_allowed():
    judge_stability.check_target(DEV_URL, allow_prod=False)


def test_a_missing_url_is_refused():
    with pytest.raises(SystemExit):
        judge_stability.check_target(None, allow_prod=False)
    with pytest.raises(SystemExit):
        judge_stability.check_target("", allow_prod=False)


def test_an_unset_fragment_refuses_a_non_local_host(monkeypatch):
    # An empty value counts as unset, and it overrides any value in a developer's .env.
    monkeypatch.setenv(FRAGMENT_VAR, "")
    get_settings.cache_clear()
    with pytest.raises(SystemExit) as refused:
        judge_stability.check_target(DEV_URL, allow_prod=False)
    assert FRAGMENT_VAR in str(refused.value)
    assert "ep-example-100" not in str(refused.value)


def test_an_unset_fragment_still_allows_a_local_host(monkeypatch):
    monkeypatch.setenv(FRAGMENT_VAR, "")
    get_settings.cache_clear()
    judge_stability.check_target("postgresql://user:pw@localhost/atsker", allow_prod=False)


def test_confirmation_is_required_before_paid_calls():
    assert judge_stability.confirm("go?", input_fn=lambda _: "") is False
    assert judge_stability.confirm("go?", input_fn=lambda _: "n") is False
    assert judge_stability.confirm("go?", input_fn=lambda _: "y") is True

    def never_called(_: str) -> str:  # pragma: no cover - asserted by the raise below
        raise AssertionError("--yes must skip the prompt")

    assert judge_stability.confirm("go?", assume_yes=True, input_fn=never_called) is True


def test_each_repeat_bypasses_the_cache(session, career, provider):
    """A cached re-run would call the provider once; bypassing calls it `repeats` times."""
    application = _stored(session, career, provider)
    before = len(provider.calls)

    result = judge_stability.measure(
        session, [application], repeats=3, model=TEST_MODEL
    )

    assert len(provider.calls) - before >= 3, "every repeat hit the provider"
    assert result["overall_max_delta"] == 0, "the stub answers identically"
    assert result["repeats"] == 3
    assert result["band"] == STABILITY_BAND


def test_the_band_is_a_provisional_integer():
    assert isinstance(STABILITY_BAND, int) and STABILITY_BAND > 0
