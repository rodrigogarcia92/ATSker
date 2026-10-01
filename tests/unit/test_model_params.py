"""Per-model request parameters as data, and Sol's request shape (PRD §7).

Everything here runs against a stubbed transport: the live run is the operator's.
`src/extract/model_params.json` maps a model id to the payload keys the client omits
for it. It ships empty, because nobody guesses which models refuse what.
"""

import json

import pytest

from src.extract import client
from src.extract.client import CallOptions, ModelParamsError, load_model_params
from src.extract.stories import StorySuggestionSchema
from src.models import LlmCall
from tests.unit.test_llm_edge import ANSWER, Answer, call, stub

SOL = "openai/gpt-6.1-sol"
GEMINI = "google/gemini-3.8-flash"
LOW = CallOptions(reasoning_effort="low")


def test_the_shipped_map_is_empty_and_is_what_the_client_loaded():
    assert load_model_params() == {}
    assert client.OMIT_BY_MODEL == {}


def test_the_payload_for_sol_carries_the_strict_schema_and_low_effort(
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
    assert payload["temperature"] == 0, "sent while the map is empty: nobody guessed a refusal"


def test_a_listed_key_is_omitted_for_that_model_only(session, test_settings, monkeypatch):
    seen = stub(monkeypatch, Answer(ANSWER))
    monkeypatch.setattr(client, "OMIT_BY_MODEL", {SOL: frozenset({"temperature"})})

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
    monkeypatch.setattr(client, "OMIT_BY_MODEL", {SOL: frozenset({"temperature"})})
    second = call(session, model=SOL, options=LOW)

    assert (first.cached, second.cached) == (False, True)
    assert len(seen) == 1


@pytest.mark.parametrize(
    ("content", "complaint"),
    [
        ("{not json", "cannot be read as JSON"),
        ('["temperature"]', "must be an object"),
        ('{"openai/gpt-6.1-sol": "temperature"}', "must map to a list"),
        ('{"openai/gpt-6.1-sol": [1]}', "must map to a list"),
        ('{"openai/gpt-6.1-sol": ["model"]}', "cannot omit model"),
    ],
)
def test_a_malformed_map_is_a_clear_startup_error(tmp_path, content, complaint):
    path = tmp_path / "model_params.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ModelParamsError) as error:
        load_model_params(path)

    assert "model_params.json" in str(error.value)
    assert complaint in str(error.value)


def test_a_missing_map_is_a_clear_startup_error(tmp_path):
    with pytest.raises(ModelParamsError, match="model_params.json cannot be read"):
        load_model_params(tmp_path / "model_params.json")


def test_a_well_formed_map_loads(tmp_path):
    path = tmp_path / "model_params.json"
    path.write_text(json.dumps({SOL: ["temperature", "seed"]}), encoding="utf-8")

    assert load_model_params(path) == {SOL: frozenset({"temperature", "seed"})}
