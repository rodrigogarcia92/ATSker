"""The model edge: caching, cost capture, schema strictness, redaction."""

from decimal import Decimal

import pytest

from src.extract import client
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    complete_json,
)
from src.extract.redaction import redact
from src.extract.stories import StorySuggestionSchema, suggest_story_links
from src.models import LlmCall

TEST_MODEL = "test/model-v1"
ANSWER = '{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}'


class Answer:
    def __init__(
        self, content: str, *, cost: str = "0.000123", prompt: int = 100, completion: int = 20
    ):
        self.content = content
        self.cost = cost
        self.prompt = prompt
        self.completion = completion

    def response(self, payload):
        return {
            "choices": [{"message": {"content": self.content}}],
            "usage": {
                "prompt_tokens": self.prompt,
                "completion_tokens": self.completion,
                "cost": self.cost,
            },
        }


def stub(monkeypatch, answer: Answer) -> list[dict]:
    seen: list[dict] = []

    def fake_post(payload, api_key):
        seen.append(payload)
        return answer.response(payload)

    monkeypatch.setattr(client, "_post", fake_post)
    return seen


def call(session, **overrides):
    values = {
        "purpose": "test",
        "prompt_version": "test_v1",
        "system": "system",
        "user": "user",
        "schema": StorySuggestionSchema,
    }
    values.update(overrides)
    return complete_json(session, **values)


def test_second_identical_call_is_served_from_the_database(session, test_settings, monkeypatch):
    seen = stub(
        monkeypatch, Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}')
    )

    first = call(session)
    second = call(session)

    assert first.cached is False
    assert second.cached is True
    assert second.data == first.data
    assert len(seen) == 1, "the cache must prevent a second network call"
    assert session.query(LlmCall).count() == 1


def test_tokens_and_cost_are_recorded(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}'))

    result = call(session)

    stored = session.query(LlmCall).one()
    assert result.prompt_tokens == 100
    assert result.completion_tokens == 20
    assert stored.cost_usd == Decimal("0.000123")
    assert stored.prompt_version == "test_v1"


def test_a_new_prompt_version_busts_the_cache(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}'))

    call(session, prompt_version="test_v1")
    call(session, prompt_version="test_v2")

    assert session.query(LlmCall).count() == 2


def test_invalid_output_fails_loudly_without_retries(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer("not json at all"))

    with pytest.raises(StructuredOutputError):
        call(session)

    assert session.query(LlmCall).count() == 0


def test_a_provider_failure_is_named_rather_than_propagated(session, test_settings, monkeypatch):
    import httpx

    def unreachable(payload, api_key):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(client, "_post", unreachable)

    with pytest.raises(ProviderUnavailable, match="connection refused"):
        call(session)

    assert session.query(LlmCall).count() == 0, "a failed call spends and caches nothing"


def test_bypassing_the_cache_makes_a_fresh_call_that_is_still_ledgered(
    session, test_settings, monkeypatch
):
    """The stability measurement needs fresh answers; the cost record still gets them."""
    seen = stub(monkeypatch, Answer(ANSWER))

    cached = call(session)
    fresh = call(session, options=CallOptions(bypass_cache=True))

    assert cached.cached is False and fresh.cached is False
    assert fresh.data == cached.data
    assert len(seen) == 2, "the cache must not be read"
    assert session.query(LlmCall).count() == 2, "and the second call is still paid for"


def test_the_seed_and_reasoning_effort_reach_the_payload(session, test_settings, monkeypatch):
    """Providers that ignore them are a measurement problem, so the request says so."""
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session, options=CallOptions(seed=4711, reasoning_effort="low"))
    payload = seen[0]

    assert payload["temperature"] == 0
    assert payload["seed"] == 4711
    assert payload["reasoning"] == {"effort": "low"}


def test_a_seeded_call_does_not_serve_an_unseeded_answer_from_the_cache(
    session, test_settings, monkeypatch
):
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session)
    call(session, options=CallOptions(seed=4711))

    assert len(seen) == 2, "the seed is part of the cache key"


def test_the_fingerprint_the_provider_echoes_is_kept(session, test_settings, monkeypatch):
    answer = Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}')
    answer.response = lambda payload: {
        "choices": [{"message": {"content": answer.content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": "0.000001"},
        "system_fingerprint": "fp_abc123",
    }
    stub(monkeypatch, answer)

    completion = call(session)

    assert completion.fingerprint == "fp_abc123"


def test_missing_model_is_reported_rather_than_defaulted(session, test_settings, monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL")
    from src.config import get_settings

    get_settings.cache_clear()
    try:
        with pytest.raises(NoModelConfigured):
            call(session)
    finally:
        get_settings.cache_clear()


def test_suggestions_drop_ids_and_skills_the_profile_cannot_justify(
    session, career, test_settings, monkeypatch
):
    """The model may only choose from what it was given; anything else is discarded."""
    payload = (
        f'{{"role_id": "{career.first_role.id}", '
        f'"bullet_ids": ["{career.first_bullet.id}", "00000000-0000-4000-8000-000000000000"], '
        '"skills": ["python", "kubernetes"], "note": "elegida"}'
    )
    stub(monkeypatch, Answer(payload))

    suggestion = suggest_story_links(
        career.first_profile.id, session, career.first_story, owner_name="Ana"
    )

    assert suggestion.role_id == career.first_role.id
    assert suggestion.bullet_ids == [career.first_bullet.id]
    assert suggestion.skills == ["python"]
    assert suggestion.note == "elegida"


def test_redaction_strips_contact_details_and_known_names():
    text = "Escribe a persona@example.com o al ++00 111 222 333. Persona Demo lideró el equipo."

    cleaned = redact(text, known_names=["Persona Demo"])

    assert "persona@example.com" not in cleaned
    assert "999" not in cleaned
    assert "Ana" not in cleaned
    assert "[email]" in cleaned and "[phone]" in cleaned and "[name]" in cleaned
