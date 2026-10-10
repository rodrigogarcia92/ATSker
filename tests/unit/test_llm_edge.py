"""The model edge: caching, cost capture, schema strictness, redaction."""

import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from src.extract import client
from src.extract.boolean import BooleanQuerySet
from src.extract.client import (
    CallOptions,
    NoModelConfigured,
    ProviderUnavailable,
    StructuredOutputError,
    TransactionHeldAcrossProviderCall,
    _prune_nulls,
    complete_json,
    nullable_paths,
    strict_schema,
)
from src.extract.gaps import GapInterpretation
from src.extract.grading import EvidenceGrading
from src.extract.jd import JDProposal
from src.extract.redaction import redact
from src.extract.resume import ResumeExtraction
from src.extract.stories import StorySuggestionSchema, suggest_story_links
from src.model_selection import ProbeAnswer
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


def test_invalid_output_fails_loudly_and_keeps_its_cost(session, test_settings, monkeypatch):
    """A.8.2: an answer the schema rejects is still a paid call, so it is recorded.

    Before A.8.2 an unparseable answer spent money and left no trace, and the next
    identical call paid again.
    """
    seen = stub(monkeypatch, Answer("not json at all"))

    with pytest.raises(StructuredOutputError):
        call(session)

    assert len(seen) == 1, "no retries were asked for"
    row = session.query(LlmCall).one()
    assert row.degenerate is True, "a rejected answer is never served back (F2.3.1)"
    assert row.cost_usd == Decimal("0.000123")
    assert row.response_json["unparsed"] is True, "the row says why there is no answer"


def test_a_runaway_answer_fails_one_call_instead_of_the_run(session, test_settings, monkeypatch):
    """A.8.2: the crash the 2026-09-25 golden run hit.

    A recursive schema made the default model nest until its answer was deeper than
    Python's parser can decode, and the `RecursionError` escaped `complete_json` and
    killed the run. It is a schema failure like any other: one call fails, one retry,
    the cost stays in the ledger, and the answer is never served back.
    """
    # Deep enough for every supported Python: 3.12 decodes 5,000 levels that 3.11 refuses.
    nested = '{"a":' * 100_000 + "1" + "}" * 100_000
    with pytest.raises(RecursionError):
        json.loads(nested)
    seen = stub(monkeypatch, Answer(nested))

    with pytest.raises(StructuredOutputError):
        call(session, retries=1)

    assert len(seen) == 2, "one retry, like every other schema violation"
    rows = session.query(LlmCall).order_by(LlmCall.id).all()
    assert [row.degenerate for row in rows] == [True, True]
    assert all(row.cost_usd == Decimal("0.000123") for row in rows), "both attempts were paid"

    session.rollback()  # the assertions above opened a read; a call refuses to start inside one
    good = stub(monkeypatch, Answer(ANSWER))
    fresh = call(session, retries=1)

    assert fresh.cached is False and len(good) == 1, "the degenerate rows never serve the cache"


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


def test_runtime_calls_pin_the_lowest_effort_from_the_setting(session, test_settings, monkeypatch):
    """Left alone, the provider picks the effort; the runtime paths do not let it."""
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session)

    assert seen[0]["reasoning"] == {"effort": "low"}, (
        "decision 27 applies to runtime calls, not only to the harness"
    )


def test_the_effort_setting_is_overridable_and_an_explicit_option_wins(
    session, test_settings, monkeypatch
):
    monkeypatch.setenv("OPENROUTER_REASONING_EFFORT", "high")
    from src.config import get_settings

    get_settings.cache_clear()
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session)
    call(session, options=CallOptions(bypass_cache=True, reasoning_effort="max"))

    assert [payload["reasoning"]["effort"] for payload in seen] == ["high", "max"]


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


def test_a_held_transaction_stops_the_call_before_it_leaves(session, test_settings, monkeypatch):
    """The connection the database kills is the caller's to release, not the client's."""
    seen = stub(monkeypatch, Answer(ANSWER))

    session.execute(text("select 1"))
    with pytest.raises(TransactionHeldAcrossProviderCall, match="test:"):
        call(session)

    session.rollback()
    session.add(
        LlmCall(purpose="pending", prompt_version="t", model="m", input_hash="h", response_json={})
    )
    with pytest.raises(TransactionHeldAcrossProviderCall, match="test:"):
        call(session)

    assert seen == [], "nothing is sent while the caller holds database state"


def test_a_ledger_failure_keeps_the_answer_and_reports_it(
    tmp_path, session, test_settings, monkeypatch
):
    """Decision 21: a paid answer is never thrown away over a bookkeeping failure."""
    seen = stub(monkeypatch, Answer(ANSWER))
    good = client._client_session
    broken = create_engine(f"sqlite:///{tmp_path}")  # a directory: nothing can connect
    opened: list[int] = []

    def flaky(bind_session):
        opened.append(1)
        return good(bind_session) if len(opened) == 1 else Session(bind=broken)

    monkeypatch.setattr(client, "_client_session", flaky)

    completion = call(session)

    assert completion.data == {"role_id": None, "bullet_ids": [], "skills": [], "note": "ok"}
    assert not completion.cached
    assert completion.ledger_error is not None
    assert len(seen) == 1, "the provider answered once, and the answer was kept"
    assert session.query(LlmCall).count() == 0, "the missing row is reported, not hidden"


def test_missing_model_is_reported_rather_than_defaulted(session, test_settings, monkeypatch):
    # An empty value, not a deleted one: a developer's .env would otherwise supply
    # a real model and the test would leave for the network.
    monkeypatch.setenv("OPENROUTER_MODEL", "")
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
    text = "Escribe a persona2@example.com o al +00 111 222 333. Persona Demo 2 lideró el equipo."

    cleaned = redact(text, known_names=["Persona Demo 2"])

    assert "persona2@example.com" not in cleaned
    assert "999" not in cleaned
    assert "Ana" not in cleaned
    assert "[email]" in cleaned and "[phone]" in cleaned and "[name]" in cleaned


def test_a_second_identical_call_after_a_degenerate_one_is_not_served_from_the_cache(
    session, test_settings, monkeypatch
):
    """F2.3.1: a marked row keeps its cost and loses its place in the cache."""
    seen = stub(monkeypatch, Answer(ANSWER))
    marked = lambda answer: True  # noqa: E731 - the caller's verdict, stated inline

    first = complete_json(
        session,
        purpose="test",
        prompt_version="test_v1",
        system="system",
        user="user",
        schema=StorySuggestionSchema,
        options=CallOptions(degenerate=marked),
    )
    second = complete_json(
        session,
        purpose="test",
        prompt_version="test_v1",
        system="system",
        user="user",
        schema=StorySuggestionSchema,
        options=CallOptions(degenerate=marked),
    )

    assert first.cached is False and second.cached is False
    assert len(seen) == 2, "the second call paid again rather than reading the marked row"
    rows = session.query(LlmCall).order_by(LlmCall.id).all()
    assert [row.degenerate for row in rows] == [True, True]
    assert all(row.cost_usd > 0 for row in rows), "the ledger keeps what was spent"


def test_the_callers_verdict_is_evaluated_before_the_ledger_write(
    session, test_settings, monkeypatch
):
    """A healthy answer under the same options is cached as usual."""
    stub(monkeypatch, Answer(ANSWER))
    verdicts: list[dict] = []

    def keep_only_empty(answer: dict) -> bool:
        verdicts.append(answer)
        return answer.get("note") == ""

    for _ in range(2):
        complete_json(
            session,
            purpose="test",
            prompt_version="test_v1",
            system="system",
            user="user",
            schema=StorySuggestionSchema,
            options=CallOptions(degenerate=keep_only_empty),
        )

    assert len(verdicts) == 1, "the judgement runs once, on the fresh answer"
    assert session.query(LlmCall).one().degenerate is False


def test_the_cache_returns_the_answer_paid_for_first(session, test_settings, monkeypatch):
    """Two rows for one hash: a bypassed run wrote the second, the first is the answer."""
    seen = stub(monkeypatch, Answer(ANSWER))
    complete_json(
        session,
        purpose="test",
        prompt_version="test_v1",
        system="system",
        user="user",
        schema=StorySuggestionSchema,
    )
    first_row = session.query(LlmCall).one()
    first_row.response_json = {"role_id": None, "bullet_ids": [], "skills": [], "note": "primero"}
    session.commit()

    # A `bypass_cache` run of the same input writes a second row for the same hash.
    complete_json(
        session,
        purpose="test",
        prompt_version="test_v1",
        system="system",
        user="user",
        schema=StorySuggestionSchema,
        options=CallOptions(bypass_cache=True),
    )
    second_row = session.query(LlmCall).order_by(LlmCall.id.desc()).first()
    second_row.response_json = {"role_id": None, "bullet_ids": [], "skills": [], "note": "segundo"}
    session.commit()
    assert first_row.id != second_row.id and len(seen) == 2

    third = complete_json(
        session,
        purpose="test",
        prompt_version="test_v1",
        system="system",
        user="user",
        schema=StorySuggestionSchema,
    )

    assert third.cached is True
    assert third.data["note"] == "primero", "the oldest row for the hash wins"


@pytest.fixture
def script_session(monkeypatch, session):
    """Point the ledger script at the test session instead of the developer's .env.

    `scripts/llm_costs.py` opens its own session through `src.db.session_scope`, which
    reads DATABASE_URL; a test must never reach that database.
    """
    from contextlib import contextmanager

    import scripts.llm_costs as llm_costs

    @contextmanager
    def scope():
        # The real `session_scope` commits on success; the script relies on that.
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    monkeypatch.setattr(llm_costs, "session_scope", scope)
    return session


def test_purging_a_hash_marks_every_row_for_it_and_keeps_the_cost(
    script_session, test_settings, monkeypatch, capsys
):
    """F2.3.1: the operator's path for an answer that is already stored."""
    from scripts.llm_costs import cmd_purge

    session = script_session
    stub(monkeypatch, Answer(ANSWER))
    call(session)
    call(session, options=CallOptions(bypass_cache=True))
    rows = session.query(LlmCall).all()
    assert len(rows) == 2 and rows[0].input_hash == rows[1].input_hash
    digest = rows[0].input_hash

    # Dry run: it prints what it would touch and writes nothing.
    assert cmd_purge(digest, confirm=False) == 0
    printed = capsys.readouterr().out
    assert digest in printed and "dry run" in printed
    assert session.query(LlmCall).filter(LlmCall.degenerate.is_(True)).count() == 0

    assert cmd_purge(digest, confirm=True) == 0

    assert session.query(LlmCall).filter(LlmCall.degenerate.is_(True)).count() == 2
    assert session.query(LlmCall).count() == 2, "the ledger keeps the rows"
    assert all(row.cost_usd == Decimal("0.000123") for row in session.query(LlmCall).all())

    # And the cache stops serving them: a matching call pays again.
    session.commit()  # the assertions above opened a read; a call refuses to start inside it
    seen = stub(monkeypatch, Answer(ANSWER))
    assert call(session).cached is False
    assert len(seen) == 1


def test_purging_an_unknown_hash_says_so_and_writes_nothing(script_session, capsys):
    from scripts.llm_costs import cmd_purge

    assert cmd_purge("0" * 64, confirm=True) == 1

    assert "no call matches" in capsys.readouterr().out
    assert script_session.query(LlmCall).count() == 0


def test_a_degenerate_extraction_is_empty_content_not_a_missing_field():
    """F2.3.1: the predicate, without a provider in sight."""
    from src.extract.resume import ResumeExtraction, is_degenerate

    assert is_degenerate(ResumeExtraction()) is True
    assert is_degenerate(ResumeExtraction(headline="Analista de datos")) is True, (
        "a headline is not parsed content"
    )
    assert is_degenerate(ResumeExtraction(summary="Cinco años con Python")) is True
    assert is_degenerate(ResumeExtraction(skills=["python"])) is False
    assert (
        is_degenerate(
            ResumeExtraction(roles=[{"employer": "Acme", "title": "Analista", "bullets": ["x"]}])
        )
        is False
    )
    assert (
        is_degenerate(ResumeExtraction(credentials=[{"kind": "education", "name": "Bachiller"}]))
        is False
    )


def test_a_degenerate_resume_extraction_raises_naming_the_input_characters(
    session, test_settings, monkeypatch
):
    """The retry is the last attempt: after it, the caller gets a named failure."""
    from src.extract.resume import EmptyExtraction, extract_resume

    stub(monkeypatch, Answer(json.dumps({"roles": [], "credentials": [], "skills": []})))
    text = "Experiencia profesional en análisis de datos. " * 12
    assert len(text) >= 200, "the fixture has to be substantial or the check does not apply"

    with pytest.raises(EmptyExtraction) as raised:
        extract_resume(session, text)

    assert raised.value.characters == len(text)
    assert str(len(text)) in str(raised.value)
    assert session.query(LlmCall).count() == 2, "both attempts are in the ledger"
    assert all(row.degenerate for row in session.query(LlmCall).all())


def test_a_short_document_with_an_empty_answer_is_not_called_degenerate(
    session, test_settings, monkeypatch
):
    """Below the threshold an empty answer is plausible: nothing to parse, nothing lost."""
    from src.extract.resume import extract_resume

    stub(monkeypatch, Answer(json.dumps({"roles": [], "credentials": [], "skills": []})))

    extraction, completion = extract_resume(session, "Analista de datos, Lima")

    assert extraction.roles == [] and completion.cached is False
    assert session.query(LlmCall).one().degenerate is False


# --- A.7: one schema every provider accepts ---------------------------------

# Every schema class `complete_json` is called with anywhere in `src/` — exactly
# what `schema=` passes. `ProbeAnswer` is the model-selection experiment's probe.
PROVIDER_SCHEMAS = [
    BooleanQuerySet,
    GapInterpretation,
    EvidenceGrading,
    JDProposal,
    ResumeExtraction,
    StorySuggestionSchema,
    ProbeAnswer,
]


def object_nodes(node):
    """Every object schema in a JSON Schema tree, `$defs` entries included."""
    if isinstance(node, list):
        for entry in node:
            yield from object_nodes(entry)
    elif isinstance(node, dict):
        if isinstance(node.get("properties"), dict):
            yield node
        for value in node.values():
            yield from object_nodes(value)


def holds_a_default(node) -> bool:
    """Whether any schema node still carries a `default` key."""
    if isinstance(node, list):
        return any(holds_a_default(entry) for entry in node)
    if not isinstance(node, dict):
        return False
    for name, value in node.items():
        if name in ("properties", "$defs"):
            if any(holds_a_default(entry) for entry in value.values()):
                return True
        elif name == "default":
            return True
        elif holds_a_default(value):
            return True
    return False


def refs_in(node) -> set[str]:
    """The names every `$ref` under a schema node points at."""
    if isinstance(node, list):
        found: set[str] = set()
        for entry in node:
            found |= refs_in(entry)
        return found
    if not isinstance(node, dict):
        return set()
    found = set()
    ref = node.get("$ref")
    if isinstance(ref, str):
        found.add(ref.rsplit("/", 1)[-1])
    for value in node.values():
        found |= refs_in(value)
    return found


def reachable(name: str, defs: dict) -> set[str]:
    """Every definition `name` can reach, following `$ref`s."""
    seen: set[str] = set()
    pending = [name]
    while pending:
        for ref in refs_in(defs.get(pending.pop(), {})):
            if ref not in seen:
                seen.add(ref)
                pending.append(ref)
    return seen


def test_the_boolean_query_schema_has_no_ref_cycle():
    """A.8.1: a recursive response model is what made strict mode ask the model for
    three keys inside every node it opened. Nothing the provider is sent may refer
    to itself, directly or through another definition."""
    strict = strict_schema(BooleanQuerySet)
    defs = strict.get("$defs") or {}

    assert defs, "the flat schema still names its query object once"
    for name in defs:
        assert name not in reachable(name, defs), f"{name} refers to itself"


@pytest.mark.parametrize("schema", PROVIDER_SCHEMAS, ids=lambda cls: cls.__name__)
def test_every_object_level_of_a_provider_schema_is_strict(schema):
    """A.7.1: `required` names every property, `additionalProperties` is false and
    no `default` survives — at the root and inside `$defs` alike. OpenAI rejects the
    whole request on any one of these; Google and DeepInfra do not."""
    strict = strict_schema(schema)

    assert not holds_a_default(strict), "a `default` anywhere is what strict mode rejects"
    nodes = list(object_nodes(strict))
    assert nodes, f"{schema.__name__} has at least one object schema"
    for node in nodes:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])


def test_an_answer_of_nulls_falls_back_to_the_models_own_defaults():
    """A.7.2: a field made nullable only so strict mode could say 'unstated' gets
    its default back; a field that genuinely accepts `null` keeps the `null`."""
    answer = {
        "language": None,
        "title": None,
        "seniority": None,
        "years_required": None,
        "must_have": None,
        "responsibilities": None,
        "location_policy": None,
    }

    pruned = _prune_nulls(answer, nullable_paths(JDProposal))

    assert pruned == {"years_required": None, "location_policy": None}, (
        "only the genuinely nullable fields keep their null"
    )
    parsed = JDProposal.model_validate(pruned)
    assert (parsed.language, parsed.title, parsed.seniority) == ("es", "", "unknown")
    assert parsed.must_have == [] and parsed.responsibilities == []
    assert parsed.years_required is None and parsed.location_policy is None


def test_nulls_inside_a_nested_object_also_become_defaults():
    """The transform reaches `$defs`, so the paths and the prune have to as well."""
    answer = {
        "headline": None,
        "roles": [{"employer": None, "title": None, "start_date": None, "bullets": None}],
        "credentials": [{"kind": None, "name": None, "field": None}],
    }

    parsed = ResumeExtraction.model_validate(
        _prune_nulls(answer, nullable_paths(ResumeExtraction))
    )

    role = parsed.roles[0]
    assert (role.employer, role.title, role.bullets) == ("", "", [])
    assert role.start_date is None, "a genuinely nullable field keeps its null"
    credential = parsed.credentials[0]
    assert (credential.kind, credential.name, credential.field) == ("unsure", "", None)


def test_the_request_carries_the_strict_schema(session, test_settings, monkeypatch):
    """What the provider sees is the strict form, not Pydantic's own."""
    seen = stub(monkeypatch, Answer(ANSWER))

    call(session)

    sent = seen[0]["response_format"]["json_schema"]
    assert sent["name"] == "StorySuggestionSchema" and sent["strict"] is True
    assert not holds_a_default(sent["schema"])
    nodes = list(object_nodes(sent["schema"]))
    assert nodes
    for node in nodes:
        assert node["additionalProperties"] is False
        assert sorted(node["required"]) == sorted(node["properties"])


def test_the_timeout_setting_reaches_the_provider_call(monkeypatch, test_settings):
    """A.7.3: a reasoning model can take minutes on three lines of posting, so the
    budget is configuration rather than a constant nobody can reach."""
    monkeypatch.setenv("OPENROUTER_TIMEOUT_SECONDS", "180")
    from src.config import get_settings

    get_settings.cache_clear()
    seen: dict[str, object] = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        raise ProviderUnavailable("stop here")

    monkeypatch.setattr("httpx.post", fake_post)

    with pytest.raises(ProviderUnavailable):
        client._post({"model": "x"}, "key")

    assert seen["timeout"] == 180.0


def test_the_default_timeout_is_the_one_the_probe_measures_against(
    monkeypatch, test_settings
):
    """`TIMEOUT_SECONDS` stays importable for `probe_model.py` and stays the budget."""
    monkeypatch.delenv("OPENROUTER_TIMEOUT_SECONDS", raising=False)
    from src.config import get_settings

    get_settings.cache_clear()
    seen: dict[str, object] = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        raise ProviderUnavailable("stop here")

    monkeypatch.setattr("httpx.post", fake_post)

    with pytest.raises(ProviderUnavailable):
        client._post({"model": "x"}, "key")

    assert seen["timeout"] == client.TIMEOUT_SECONDS


def test_the_ledger_row_records_the_latency_of_the_request(session, test_settings, monkeypatch):
    import time

    def slow_post(payload, api_key):
        time.sleep(0.03)
        return Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}').response(
            payload
        )

    monkeypatch.setattr(client, "_post", slow_post)

    call(session)

    assert session.query(LlmCall).one().latency_ms >= 25


def test_a_cache_hit_writes_no_row_and_so_no_latency(session, test_settings, monkeypatch):
    stub(monkeypatch, Answer('{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}'))
    call(session)

    call(session)

    assert session.query(LlmCall).count() == 1


def test_an_unparsed_answer_carries_its_latency_too(session, test_settings, monkeypatch):
    import time

    def slow_bad(payload, api_key):
        time.sleep(0.03)
        return Answer("not json at all").response(payload)

    monkeypatch.setattr(client, "_post", slow_bad)

    with pytest.raises(StructuredOutputError):
        call(session)

    row = session.query(LlmCall).one()
    assert row.degenerate is True and row.latency_ms >= 25


def test_a_retry_records_the_time_of_the_request_whose_answer_is_stored(
    session, test_settings, monkeypatch
):
    import time

    delays = iter([0.12, 0.02])
    answers = iter(["not json", '{"role_id": null, "bullet_ids": [], "skills": [], "note": "ok"}'])

    def post(payload, api_key):
        time.sleep(next(delays))
        return Answer(next(answers)).response(payload)

    monkeypatch.setattr(client, "_post", post)

    call(session, retries=1)

    stored = session.query(LlmCall).filter(LlmCall.degenerate.is_(False)).one()
    assert 15 <= stored.latency_ms < 100, "the second request alone, not the sum"
