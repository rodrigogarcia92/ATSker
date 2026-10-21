"""Per-model profiles as data, and the request shape each one produces (PRD §7).

Everything here runs against a stubbed transport: the live run is the operator's.
`src/extract/model_profiles.json` maps a model id to what the client must send for it;
a model absent from the file behaves exactly as the client always has.
"""

import hashlib
import json

import pytest

from src.extract import client
from src.extract.client import (
    CallOptions,
    ModelProfile,
    ModelProfileError,
    load_model_profiles,
)
from src.extract.stories import StorySuggestionSchema
from src.models import LlmCall
from tests.unit.test_llm_edge import ANSWER, Answer, call, stub

SOL = "openai/gpt-6.1-sol"
GEMINI = "google/gemini-3.8-flash"
HAIKU = "anthropic/claude-haiku-5.5"
DEEPSEEK = "deepseek/deepseek-v4.1-flash-1017"
LOW = CallOptions(reasoning_effort="low")


def test_the_shipped_file_is_what_the_client_loaded():
    profiles = load_model_profiles()

    assert profiles == client.MODEL_PROFILES
    assert set(profiles) == {HAIKU, GEMINI, DEEPSEEK}
    assert profiles[HAIKU].omit == frozenset({"temperature"})
    assert profiles[HAIKU].reasoning["default"] == "low"
    assert profiles[HAIKU].cache_system is True
    assert profiles[GEMINI].reasoning == {"default": "low"}
    assert profiles[DEEPSEEK].reasoning == {"default": "off"}


def test_the_payload_for_a_model_without_a_profile_is_todays(
    session, test_settings, monkeypatch
):
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session, model=SOL, options=LOW)

    (payload,) = seen
    assert payload["model"] == SOL
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": client._schema_for(StorySuggestionSchema),
    }
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["temperature"] == 0, "sent when no profile refuses it"


def test_a_listed_key_is_omitted_for_that_model_only(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))
    monkeypatch.setattr(
        client, "MODEL_PROFILES", {SOL: ModelProfile(omit=frozenset({"temperature"}))}
    )

    call(session, model=SOL, options=LOW)
    call(session, model=GEMINI, options=LOW)

    sol, gemini = seen
    assert "temperature" not in sol
    assert sol["reasoning"] == {"effort": "low"}
    assert sol["response_format"]["json_schema"]["strict"] is True
    assert [message["role"] for message in sol["messages"]] == ["system", "user"]
    assert gemini["temperature"] == 0, "another model keeps it"


def test_a_grading_cached_under_gemini_is_not_served_to_sol(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))

    first = call(session, model=GEMINI, options=LOW)
    again = call(session, model=GEMINI, options=LOW)
    sol = call(session, model=SOL, options=LOW)

    assert (first.cached, again.cached) == (False, True)
    assert sol.cached is False, "the model id is part of the cache key"
    assert [payload["model"] for payload in seen] == [GEMINI, SOL]
    session.commit()
    assert sorted(row.model for row in session.query(LlmCall)) == [GEMINI, SOL]


def test_omitting_a_key_does_not_change_the_cache_key(session, test_settings, monkeypatch):
    """The omission is a transport detail: the hash composition is untouched."""
    seen = stub(monkeypatch, Answer(ANSWER))

    first = call(session, model=SOL, options=LOW)
    monkeypatch.setattr(
        client, "MODEL_PROFILES", {SOL: ModelProfile(omit=frozenset({"temperature"}))}
    )
    second = call(session, model=SOL, options=LOW)

    assert (first.cached, second.cached) == (False, True)
    assert len(seen) == 1


def test_haiku_grading_carries_its_provider_cap_and_cached_system_prompt(
    session, test_settings, monkeypatch
):
    seen = stub(monkeypatch, Answer(ANSWER))

    completion = call(session, model=HAIKU, purpose="evidence_grade")

    (payload,) = seen
    assert "temperature" not in payload, "the profile omits it"
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["provider"] == {"order": ["azure", "anthropic"], "allow_fallbacks": True}
    assert payload["max_tokens"] == 8000
    assert payload["messages"][0] == {
        "role": "system",
        "content": [
            {"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}
        ],
    }
    assert payload["messages"][1] == {"role": "user", "content": "user"}
    assert completion.reasoning_effort == "low"


def test_haiku_turns_reasoning_off_for_a_gap_interpretation(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))

    completion = call(session, model=HAIKU, purpose="gap_interpret")

    (payload,) = seen
    assert payload["reasoning"] == {"enabled": False}
    assert completion.reasoning_effort == "off"


def test_gemini_sends_exactly_todays_payload(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session, model=GEMINI)

    expected = {
        "model": GEMINI,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "user"},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": client._schema_for(StorySuggestionSchema),
        },
        "usage": {"include": True},
        "reasoning": {"effort": "low"},
    }
    assert seen == [expected]


def test_deepseek_sends_no_reasoning_through_named_providers(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session, model=DEEPSEEK)

    (payload,) = seen
    assert payload["reasoning"] == {"enabled": False}
    assert payload["provider"] == {
        "order": ["together", "baseten"],
        "allow_fallbacks": False,
        "data_collection": "deny",
    }
    assert payload["max_tokens"] == 8000
    assert payload["temperature"] == 0, "the profile does not omit it"


def test_an_explicit_effort_wins_over_the_profile(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))

    completion = call(
        session, model=HAIKU, purpose="gap_interpret", options=CallOptions(reasoning_effort="high")
    )

    (payload,) = seen
    assert payload["reasoning"] == {"effort": "high"}
    assert completion.reasoning_effort == "high"


def test_a_retry_appends_to_a_cached_system_message(session, test_settings, monkeypatch):
    answers = iter([Answer("not json"), Answer(ANSWER)])
    seen: list[dict] = []

    def fake_post(payload, api_key):
        seen.append(payload)
        return next(answers).response(payload)

    monkeypatch.setattr(client, "_post", fake_post)

    call(session, model=HAIKU, purpose="evidence_grade", retries=1)

    assert len(seen) == 2
    messages = seen[-1]["messages"]
    assert [message["role"] for message in messages] == ["system", "user", "assistant", "user"]
    assert isinstance(messages[0]["content"], list), "still the cached text part"
    assert messages[1] == {"role": "user", "content": "user"}


def _old_digest(*parts: str) -> str:
    """The cache key as the client computed it before profiles existed."""
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def test_gemini_keeps_the_cache_digest_history_gave_it(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer(ANSWER))

    call(session, model=GEMINI, purpose="evidence_grade")
    session.commit()

    (row,) = session.query(LlmCall).all()
    assert row.input_hash == _old_digest(
        "evidence_grade", "test_v1", GEMINI, "system", "user", "reasoning=low"
    )


def test_haiku_hashes_each_purpose_with_its_own_effort(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer(ANSWER))

    call(session, model=HAIKU, purpose="evidence_grade")
    call(session, model=HAIKU, purpose="gap_interpret")
    session.commit()

    hashes = {row.purpose: row.input_hash for row in session.query(LlmCall)}
    assert hashes["evidence_grade"] == _old_digest(
        "evidence_grade", "test_v1", HAIKU, "system", "user", "reasoning=low"
    )
    assert hashes["gap_interpret"] == _old_digest(
        "gap_interpret", "test_v1", HAIKU, "system", "user", "reasoning=off"
    )


@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        ("{not json", "cannot be read as JSON"),
        ('["temperature"]', "must be an object mapping a model id to a profile"),
        ('{"openai/gpt-6.1-sol": "temperature"}', "profile: must be an object"),
        ('{"openai/gpt-6.1-sol": {"omit": "temperature"}}', "omit: must be a list"),
        ('{"openai/gpt-6.1-sol": {"omit": [1]}}', "omit: must be a list"),
        ('{"openai/gpt-6.1-sol": {"omit": ["model"]}}', "omit: cannot contain model"),
        ('{"openai/gpt-6.1-sol": {"omit": ["messages"]}}', "omit: cannot contain messages"),
        ('{"openai/gpt-6.1-sol": {"maximum": 10}}', "maximum: unknown key"),
        (
            '{"openai/gpt-6.1-sol": {"reasoning": {"gap_interpret": "max"}}}',
            "reasoning['gap_interpret']",
        ),
        ('{"openai/gpt-6.1-sol": {"reasoning": "off"}}', "reasoning: must be an object"),
        ('{"openai/gpt-6.1-sol": {"max_tokens": 0}}', "max_tokens: must be a positive"),
        ('{"openai/gpt-6.1-sol": {"max_tokens": true}}', "max_tokens: must be a positive"),
        ('{"openai/gpt-6.1-sol": {"provider": ["azure"]}}', "provider: must be an object"),
        ('{"openai/gpt-6.1-sol": {"cache_system": "yes"}}', "cache_system: must be true"),
    ],
)
def test_a_malformed_file_is_a_clear_startup_error(tmp_path, content, complaint):
    path = tmp_path / "model_profiles.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ModelProfileError) as error:
        load_model_profiles(path)

    assert "model_profiles.json" in str(error.value)
    assert complaint in str(error.value)


def test_a_missing_file_is_a_clear_startup_error(tmp_path):
    with pytest.raises(ModelProfileError, match="model_profiles.json cannot be read"):
        load_model_profiles(tmp_path / "model_profiles.json")


def test_a_well_formed_file_loads(tmp_path):
    path = tmp_path / "model_profiles.json"
    path.write_text(
        json.dumps(
            {
                SOL: {
                    "omit": ["temperature", "seed"],
                    "provider": {"order": ["azure"]},
                    "reasoning": {"default": "minimal", "gap_interpret": "off"},
                    "max_tokens": 900,
                    "cache_system": True,
                }
            }
        ),
        encoding="utf-8",
    )

    assert load_model_profiles(path) == {
        SOL: ModelProfile(
            omit=frozenset({"temperature", "seed"}),
            provider={"order": ["azure"]},
            reasoning={"default": "minimal", "gap_interpret": "off"},
            max_tokens=900,
            cache_system=True,
        )
    }
