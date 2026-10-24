"""OpenRouter chat completions: structured output, temperature 0, cached by hash.

Cost and token counts land in `llm_calls` on every uncached call, which is where
PRD 7's cost instrumentation comes from. The stored response doubles as the cache,
so a repeat of the same purpose, prompt version, model and input makes no network
call and returns byte-identical output.

No transaction crosses the network here. The caller releases its own reads before
calling — `complete_json` refuses to run otherwise — and the ledger row is written
on a connection of the client's own afterwards. A transaction left open while the
provider thinks is the one the database kills mid-flight (2026-09-20, defect 1).
"""

import hashlib
import json
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.config import Settings, get_settings
from src.models import LlmCall

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# What each model needs, as data (PRD §7): data, not code, so a model that refuses a
# payload key — a reasoning model that rejects `temperature` with a 400 — or needs its
# providers pinned is one entry here rather than a branch. A model absent from the file
# behaves exactly as the client always has.
MODEL_PROFILES_PATH = Path(__file__).with_name("model_profiles.json")
# The request is meaningless without these, so a model cannot be configured to lose them.
_NEVER_OMITTED = frozenset({"model", "messages"})
# What OpenRouter accepts as a reasoning effort, plus `off` for no reasoning at all.
REASONING_LEVELS = frozenset({"off", "minimal", "low", "medium", "high"})
_PROFILE_KEYS = frozenset({"omit", "provider", "reasoning", "max_tokens", "cache_system"})
# The default `Settings.openrouter_timeout_seconds` starts from, kept importable so
# `fixtures/golden/probe_model.py` can measure against the app's own budget.
TIMEOUT_SECONDS = 60.0

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelProfileError(RuntimeError):
    """`model_profiles.json` is unreadable or holds an entry the request cannot use."""


@dataclass(frozen=True)
class ModelProfile:
    """One model's request requirements (PRD §7).

    `omit` names payload keys to leave out; `provider` is OpenRouter's routing block,
    copied as written; `reasoning` maps a purpose to an effort (`"off"` sends
    `enabled: false`), with `"default"` for every purpose not named; `max_tokens`
    caps the answer; `cache_system` marks the system prompt for prompt caching.
    """

    omit: frozenset[str] = frozenset()
    provider: dict[str, Any] | None = None
    reasoning: Mapping[str, str] = field(default_factory=dict)
    max_tokens: int | None = None
    cache_system: bool = False


def load_model_profiles(path: Path = MODEL_PROFILES_PATH) -> dict[str, ModelProfile]:
    """Read the per-model profiles, or fail naming the file, the model and the key."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelProfileError(f"{path.name} cannot be read as JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ModelProfileError(
            f'{path.name} must be an object mapping a model id to a profile, e.g. '
            '{"anthropic/claude-haiku-5.5": {"reasoning": {"default": "low"}}}'
        )

    def bad(model: str, key: str, detail: str) -> ModelProfileError:
        return ModelProfileError(f"{path.name}: {model!r}: {key}: {detail}")

    profiles: dict[str, ModelProfile] = {}
    for model, entry in raw.items():
        if not isinstance(entry, dict):
            raise bad(model, "profile", "must be an object")
        unknown = sorted(set(entry) - _PROFILE_KEYS)
        if unknown:
            raise bad(
                model,
                unknown[0],
                f"unknown key; a profile has {', '.join(sorted(_PROFILE_KEYS))}",
            )
        omit = entry.get("omit", [])
        if not isinstance(omit, list) or not all(isinstance(key, str) for key in omit):
            raise bad(model, "omit", "must be a list of payload keys")
        forbidden = sorted(_NEVER_OMITTED & set(omit))
        if forbidden:
            raise bad(model, "omit", f"cannot contain {', '.join(forbidden)}; the request needs it")
        provider = entry.get("provider")
        if provider is not None and not isinstance(provider, dict):
            raise bad(model, "provider", "must be an object")
        reasoning = entry.get("reasoning", {})
        if not isinstance(reasoning, dict):
            raise bad(model, "reasoning", "must be an object mapping a purpose to an effort")
        for purpose, level in reasoning.items():
            if not isinstance(level, str) or level not in REASONING_LEVELS:
                raise bad(
                    model,
                    f"reasoning[{purpose!r}]",
                    f"{level!r} is not one of {', '.join(sorted(REASONING_LEVELS))}",
                )
        max_tokens = entry.get("max_tokens")
        if max_tokens is not None and (
            not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0
        ):
            raise bad(model, "max_tokens", "must be a positive integer")
        cache_system = entry.get("cache_system", False)
        if not isinstance(cache_system, bool):
            raise bad(model, "cache_system", "must be true or false")
        profiles[model] = ModelProfile(
            omit=frozenset(omit),
            provider=provider,
            reasoning=dict(reasoning),
            max_tokens=max_tokens,
            cache_system=cache_system,
        )
    return profiles


# Read once, when the client is first imported: a malformed file stops the app at
# startup with the file's name, never on the first paid call.
MODEL_PROFILES: dict[str, ModelProfile] = load_model_profiles()


class NoModelConfigured(RuntimeError):
    """OPENROUTER_MODEL is empty. The model is chosen by measurement (PRD 7), not default."""


class StructuredOutputError(RuntimeError):
    """The provider returned something the schema does not accept."""


class ProviderUnavailable(RuntimeError):
    """The provider could not be reached, or answered with an error status.

    Named rather than propagated raw so the UI can say what happened instead of
    showing a stack trace, and so the caller can tell a transport failure from a
    model that answered badly.
    """


class TransactionHeldAcrossProviderCall(RuntimeError):
    """The caller holds a transaction (or uncommitted changes) when the call starts.

    A transaction held across the HTTP request sits idle while the provider thinks,
    and that is the connection the database kills mid-flight — the failure that
    made a paid extraction unrecordable. The boundary belongs to the caller's unit
    of work, so the client will not commit someone else's transaction: it stops
    before the network call and names the caller instead.
    """


class LedgerWriteError(RuntimeError):
    """The paid call could not be written to `llm_calls` on the client's own connection.

    Caught inside `complete_json`, which keeps the answer and reports the gap as
    `Completion.ledger_error`: throwing away something already paid for is worse
    than a missing ledger row (decision 21).
    """


# The paid call's id, kept inside `response_json` because `llm_calls` has no column
# for it and queue R adds no migration. It is what makes the ledger write's retry
# idempotent, and it is stripped before a cached row is served as an answer.
CALL_ID_KEY = "_call_id"


@dataclass(frozen=True)
class CallOptions:
    """How a caller wants its model calls made.

    Defaults are production behaviour: the content-hash cache is read, temperature
    is 0, and the reasoning effort is pinned by `OPENROUTER_REASONING_EFFORT` (low,
    decision 27) rather than left to the provider. The model-selection experiment
    turns the cache off so that repeated runs measure the judge rather than the
    cache, and pins a seed and a reasoning effort so the repeats are as comparable
    as the provider allows; an explicit value here wins over the setting.

    `degenerate` is the caller's judgement about its *own* answer (F2.3.1): the
    client does not know what "empty" means for a given purpose, so the caller
    supplies a predicate over the parsed answer, evaluated before the ledger write.
    A row it rejects keeps its cost but is never served from the cache again.
    """

    bypass_cache: bool = False
    seed: int | None = None
    reasoning_effort: str | None = None
    degenerate: Callable[[dict[str, Any]], bool] | None = None
    # Whose call it is (F2.8): recorded on the ledger row so "Eliminar todo" can
    # redact that profile's personal answers. Attribution rides the options the
    # analysis path already forwards unchanged, so the frozen scorer files need no
    # edit (queue B.2's decision); the cache lookup deliberately never filters by
    # it — same input and prompt version stay one cache entry, whatever the profile.
    profile_id: uuid.UUID | None = None


@dataclass(frozen=True)
class Completion:
    """One call site's answer, and what it cost.

    `purpose`, `prompt_version` and `model` travel with the answer so the caller
    can record the analysis's prompt versions and cost without re-deriving them.
    `fingerprint` is whatever the provider echoed to identify the backend
    (OpenRouter's `system_fingerprint`), which is how a caller can tell whether a
    seeded request was honoured or merely accepted. `ledger_error` is None when the
    paid call reached `llm_calls`; otherwise it says why it did not, and the caller
    surfaces that instead of pretending the record is complete.
    """

    data: dict[str, Any]
    cached: bool
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    purpose: str
    prompt_version: str
    model: str
    # What the call was actually made with, not what was asked for: the request's
    # effort falls back to the environment's, and a run's CSV reports the effective
    # values so two runs are never compared across a setting nobody named.
    reasoning_effort: str | None = None
    fingerprint: str | None = None
    ledger_error: str | None = None
    # What the request to the provider took, in milliseconds (F12.4): the same value
    # the ledger row carries, and 0 when the cache answered instead of the provider.
    latency_ms: int | None = None


def _post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Single choke point for the network, so tests can replace it."""
    response = httpx.post(
        ENDPOINT,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=get_settings().openrouter_timeout_seconds,
    )
    response.raise_for_status()
    return response.json()


def _schema_for(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": schema.__name__,
        "strict": True,
        "schema": strict_schema(schema),
    }


def _accepts_null(node: Any) -> bool:
    """True when a JSON Schema node already allows `null` on its own."""
    if not isinstance(node, dict):
        return False
    if node.get("type") == "null":
        return True
    return any(
        isinstance(entry, dict) and entry.get("type") == "null"
        for entry in node.get("anyOf") or ()
    )


def strict_schema(schema: type[BaseModel]) -> dict[str, Any]:
    """OpenAI strict mode's shape, derived from Pydantic's rather than written (A.7.1).

    Strict mode wants `required` to name every property, `additionalProperties`
    false, and no `default` anywhere. Pydantic omits defaulted fields from
    `required`, emits `default` keys and leaves `additionalProperties` alone —
    which Google and DeepInfra accept and OpenAI rejects outright (2026-09-25).
    Closing the gap here rather than in the models keeps one schema for every
    provider: a property that was optional and did not accept `null` becomes
    nullable so a strict model can still say "unstated", and `nullable_paths` with
    `_prune_nulls` turns those `null`s back into the field's own default before
    Pydantic sees them.
    """
    root = schema.model_json_schema()

    def transform(node: Any) -> Any:
        if isinstance(node, list):
            return [transform(entry) for entry in node]
        if not isinstance(node, dict):
            return node

        out: dict[str, Any] = {}
        for name, value in node.items():
            if name == "default":
                continue
            if name in ("properties", "$defs") and isinstance(value, dict):
                # These map *names* to schemas: their keys are not keywords, so a
                # property literally called `default` survives here.
                out[name] = {key: transform(entry) for key, entry in value.items()}
            else:
                out[name] = transform(value)

        properties = out.get("properties")
        if not isinstance(properties, dict):
            return out
        required = set(node.get("required") or ())
        for name, prop in list(properties.items()):
            if name in required or _accepts_null(prop):
                continue
            wrapper: dict[str, Any] = {"anyOf": [prop, {"type": "null"}]}
            if isinstance(prop, dict) and isinstance(prop.get("description"), str):
                wrapper["description"] = prop["description"]
            properties[name] = wrapper
        out["required"] = sorted(properties)
        out["additionalProperties"] = False
        return out

    return transform(root)


@cache
def nullable_paths(schema: type[BaseModel]) -> frozenset[tuple[str, ...]]:
    """Paths of the properties `strict_schema` had to make nullable (A.7.2).

    A path is the chain of property names from the root, with a list contributing
    no step — `roles[].start_date` is `("roles", "start_date")`. Cached per schema
    class: every answer is pruned against it and the shape never changes.
    """
    root = schema.model_json_schema()
    defs = root.get("$defs") or {}
    found: set[tuple[str, ...]] = set()

    def walk(node: Any, path: tuple[str, ...], stack: tuple[str, ...]) -> None:
        if isinstance(node, list):
            for entry in node:
                walk(entry, path, stack)
            return
        if not isinstance(node, dict):
            return
        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            # A recursive response model would grow its paths without end; the
            # cycle is cut here. No schema sent to a provider is recursive.
            if name not in stack:
                walk(defs.get(name), path, (*stack, name))
            return
        for name, entry in (node.get("properties") or {}).items():
            here = (*path, name)
            if name not in set(node.get("required") or ()) and not _accepts_null(entry):
                found.add(here)
            walk(entry, here, stack)
        for key in ("anyOf", "oneOf", "allOf", "items"):
            walk(node.get(key), path, stack)

    walk(root, (), ())
    return frozenset(found)


def _prune_nulls(answer: Any, paths: frozenset[tuple[str, ...]], path: tuple[str, ...] = ()) -> Any:
    """Drop the `null`s strict mode forced the schema to accept (A.7.2).

    Such a field has a default of its own and `null` must not overwrite it. A
    field that genuinely accepts `null` is never in `paths`, so its `null` stays.
    """
    if isinstance(answer, list):
        return [_prune_nulls(entry, paths, path) for entry in answer]
    if not isinstance(answer, dict):
        return answer
    cleaned: dict[str, Any] = {}
    for name, value in answer.items():
        here = (*path, name)
        if value is None and here in paths:
            continue
        cleaned[name] = _prune_nulls(value, paths, here)
    return cleaned


def _input_hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def _client_session(session: Session) -> Session:
    """A session of its own, on the caller's engine.

    The client's database work is its own unit of work: neither the cache read nor
    the ledger write rides — or ends — a transaction the caller owns.
    """
    return Session(bind=session.get_bind())


def _refuse_held_transaction(session: Session, purpose: str) -> None:
    """Stop before the network call when the caller still holds database state.

    A live transaction is the one the database kills while the provider thinks;
    uncommitted changes count too, because the call sequence must not flush them by
    accident. Naming the caller is the point: the fix is a commit or a rollback at
    the call site, not a retry here.
    """
    if session.in_transaction() or session.new or session.dirty or session.deleted:
        raise TransactionHeldAcrossProviderCall(
            f"{purpose}: the caller holds a transaction or uncommitted changes when the "
            "provider call starts; commit or roll back first"
        )


def _ledger_has_call(session: Session, *, input_hash: str, call_id: uuid.UUID) -> bool:
    """True when the row for `call_id` is already in the ledger.

    A commit can *succeed* and still raise (SQLite's "commit returned NULL" under
    threads is the sighting; Postgres can do the same on a lost response). The
    retry then used to write the same paid call twice — a duplicate row and, worse,
    a row the cache serves as if it were a second call.

    The id lives in `response_json` (`_call_id`) rather than in a column of its own:
    a column would need a migration, and queue R has none. The lookup reads the rows
    of this input hash — at most a handful — and compares in Python, so no backend's
    JSON syntax is involved.
    """
    try:
        with _client_session(session) as reader:
            rows = reader.scalars(
                select(LlmCall.response_json).where(LlmCall.input_hash == input_hash)
            ).all()
        return any((row or {}).get(CALL_ID_KEY) == str(call_id) for row in rows)
    except SQLAlchemyError:
        # The database is unreachable: that is not evidence the row exists, so the
        # retry goes ahead and reports the failure if it fails again.
        return False


def _write_ledger(
    session: Session,
    *,
    call_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    model: str,
    input_hash: str,
    response_json: dict[str, Any],
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    degenerate: bool = False,
    profile_id: uuid.UUID | None = None,
    latency_ms: int | None = None,
) -> None:
    """Write the paid call's row on the client's own connection, with one retry.

    The row is also the cache entry (decision 21), so the retry is not only about
    the record: it is what stops the next identical call from paying again. A fresh
    connection cannot be the one the database killed while the provider worked.

    The retry is idempotent (R13.1): `call_id` is the paid call's own id, generated
    once before its first attempt, so a commit that raised after writing is found on
    the retry and not written again.

    `degenerate` is the caller's verdict on its own answer (F2.3.1). The row is
    written either way — the call was paid for — and the flag is what excludes it
    from the cache lookup.
    """
    error: SQLAlchemyError | None = None
    for attempt in range(2):
        if attempt and _ledger_has_call(session, input_hash=input_hash, call_id=call_id):
            return
        try:
            with _client_session(session) as ledger:
                ledger.add(
                    LlmCall(
                        purpose=purpose,
                        prompt_version=prompt_version,
                        model=model,
                        input_hash=input_hash,
                        response_json={**response_json, CALL_ID_KEY: str(call_id)},
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost_usd,
                        degenerate=degenerate,
                        profile_id=profile_id,
                        latency_ms=latency_ms,
                    )
                )
                ledger.commit()
            return
        except SQLAlchemyError as exc:
            error = exc
    raise LedgerWriteError(f"the call could not be recorded: {error}") from error


def _record_unparsed(
    session: Session,
    *,
    call_id: uuid.UUID,
    purpose: str,
    prompt_version: str,
    model: str,
    input_hash: str,
    error: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    profile_id: uuid.UUID | None,
    latency_ms: int | None = None,
) -> None:
    """Ledger a paid answer the schema could not parse, marked degenerate (A.8.2).

    The answer itself is not kept — there is no shape to keep and a runaway one is
    enormous — so the row records why it failed. What matters is the same as for any
    other rejected answer (F2.3.1): the cost stays and the row never serves the cache.
    A bookkeeping failure here cannot be reported through a `Completion` (there is
    none), and the `StructuredOutputError` the caller is about to receive is the
    honest report, so it is swallowed rather than replacing it.
    """
    try:
        _write_ledger(
            session,
            call_id=call_id,
            purpose=purpose,
            prompt_version=prompt_version,
            model=model,
            input_hash=input_hash,
            response_json={"unparsed": True, "error": error[:500]},
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            degenerate=True,
            profile_id=profile_id,
            latency_ms=latency_ms,
        )
    except LedgerWriteError:
        pass


def effective_effort(
    profile: ModelProfile | None, purpose: str, opts: CallOptions, settings: Settings
) -> str | None:
    """The reasoning effort this call is made with, first source that names one.

    An explicit option wins; then the model's own entry for this purpose, its
    default, the environment's setting. `None` sends no `reasoning` key at all,
    leaving the provider's own default — which is what a model without a profile
    has always done.
    """
    if opts.reasoning_effort:
        return opts.reasoning_effort
    if profile is not None:
        if purpose in profile.reasoning:
            return profile.reasoning[purpose]
        if "default" in profile.reasoning:
            return profile.reasoning["default"]
    return settings.openrouter_reasoning_effort or None


def build_payload(
    chosen: str,
    purpose: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    opts: CallOptions,
    settings: Settings,
) -> tuple[dict[str, Any], str | None]:
    """The request body for one call, and the effort it is being made with (PRD §7).

    The model's profile decides what it needs beyond the common shape: a provider
    routing block, an answer cap, prompt caching for the system message, and the
    payload keys it refuses. A model without a profile gets the payload the client
    has always sent.
    """
    profile = MODEL_PROFILES.get(chosen)
    effort = effective_effort(profile, purpose, opts, settings)

    system_content: str | list[dict[str, Any]] = system
    if profile is not None and profile.cache_system:
        # The system prompt is the stable half of every call and the larger one: an
        # ephemeral breakpoint is what lets the provider serve it from its cache.
        system_content = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]

    payload: dict[str, Any] = {
        "model": chosen,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_schema", "json_schema": _schema_for(schema)},
        "usage": {"include": True},
    }
    if opts.seed is not None:
        payload["seed"] = opts.seed
    if effort is not None:
        # `off` is not an effort the API knows: it is no reasoning at all.
        payload["reasoning"] = {"enabled": False} if effort == "off" else {"effort": effort}
    if profile is not None:
        if profile.provider is not None:
            payload["provider"] = profile.provider
        if profile.max_tokens is not None:
            payload["max_tokens"] = profile.max_tokens
        for omitted in profile.omit:
            payload.pop(omitted, None)
    return payload, effort


def complete_json(
    session: Session,
    *,
    purpose: str,
    prompt_version: str,
    system: str,
    user: str,
    schema: type[SchemaT],
    model: str | None = None,
    retries: int = 0,
    options: CallOptions | None = None,
) -> Completion:
    opts = options or CallOptions()
    _refuse_held_transaction(session, purpose)
    settings = get_settings()
    chosen = model or (settings.openrouter_model or "").strip()
    if not chosen:
        raise NoModelConfigured("OPENROUTER_MODEL is not set")
    if settings.openrouter_api_key is None:
        raise NoModelConfigured("OPENROUTER_API_KEY is not set")

    payload, effort = build_payload(chosen, purpose, system, user, schema, opts, settings)

    # The key is what the caller asked for, never how it is transported: the model's
    # provider routing, answer cap and prompt caching do not change the answer, so
    # they stay out of the hash and a cached answer survives a profile edit.
    key = [purpose, prompt_version, chosen, system, user]
    if opts.seed is not None:
        key.append(f"seed={opts.seed}")
    if effort is not None:
        key.append(f"reasoning={effort}")
    digest = _input_hash(*key)

    cached = None
    if not opts.bypass_cache:
        with _client_session(session) as reader:
            cached = reader.scalar(
                select(LlmCall)
                .where(
                    LlmCall.purpose == purpose,
                    LlmCall.prompt_version == prompt_version,
                    LlmCall.input_hash == digest,
                    # F2.3.1: a rejected answer keeps its cost but is never served
                    # back, or the first bad answer would be the permanent one.
                    LlmCall.degenerate.is_(False),
                )
                # Duplicate rows for one hash exist — a `bypass_cache` run writes a
                # second one — so the lookup has to be deterministic: answer first
                # paid for, first returned. Without this the planner decided.
                .order_by(LlmCall.id)
            )
    if cached is not None:
        # R13.1: the row's own id is bookkeeping, never part of the answer.
        data = dict(cached.response_json)
        data.pop(CALL_ID_KEY, None)
        return Completion(
            data=data,
            cached=True,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            purpose=purpose,
            prompt_version=prompt_version,
            model=chosen,
            reasoning_effort=effort,
            latency_ms=0,
        )

    attempt = 0
    while True:
        # R13.1: one id per paid response, minted before its first ledger attempt.
        # An answer the schema rejects and the next attempt's answer are two rows
        # (each was paid for), so they cannot share an id; a retry of one write does.
        call_id = uuid.uuid4()
        try:
            started = time.perf_counter()
            body = _post(payload, settings.openrouter_api_key.get_secret_value())
            latency_ms = round((time.perf_counter() - started) * 1000)
        except httpx.HTTPError as exc:
            # A transport or status failure spends nothing and caches nothing, but
            # the caller still needs to name it rather than fail as an unknown 500.
            raise ProviderUnavailable(str(exc)) from exc
        message = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        cost = Decimal(str(usage.get("cost") or 0))
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        try:
            # A.7.2: strict mode made some optional fields nullable so the model
            # could say "unstated". Those `null`s are dropped here and the field's
            # own default applies; a `null` the schema genuinely allows stays.
            data = _prune_nulls(json.loads(message), nullable_paths(schema))
            parsed = schema.model_validate(data)
        except (ValueError, RecursionError) as exc:
            # A.8.2: `ValueError` covers both `json.JSONDecodeError` and Pydantic's
            # `ValidationError`; `RecursionError` is a runaway answer — the model
            # nested past what Python's parser can decode, which is a schema failure
            # like any other and must fail one call, not the run. It was paid for,
            # so the row is written with its cost and marked degenerate (F2.3.1):
            # the cost stays in the ledger and the answer is never served back.
            _record_unparsed(
                session,
                call_id=call_id,
                purpose=purpose,
                prompt_version=prompt_version,
                model=chosen,
                input_hash=digest,
                error=str(exc),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                profile_id=opts.profile_id,
                latency_ms=latency_ms,
            )
            if attempt < retries:
                attempt += 1
                payload["messages"] = [
                    *payload["messages"],
                    {"role": "assistant", "content": message},
                    {"role": "user", "content": "That did not match the schema. Answer again."},
                ]
                continue
            raise StructuredOutputError(str(exc)) from exc
        break

    answer = parsed.model_dump(mode="json")
    # The caller knows what an empty answer means for its own purpose; the client
    # only records the verdict. Evaluated here, once, so one code path marks the row
    # and nothing else about the call changes.
    degenerate = bool(opts.degenerate and opts.degenerate(answer))

    ledger_error: str | None = None
    try:
        _write_ledger(
            session,
            call_id=call_id,
            purpose=purpose,
            prompt_version=prompt_version,
            model=chosen,
            input_hash=digest,
            response_json=answer,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            degenerate=degenerate,
            profile_id=opts.profile_id,
            latency_ms=latency_ms,
        )
    except LedgerWriteError as exc:
        # The answer was paid for: return it, and let the caller surface that the
        # record is missing rather than fail a request that already has its answer.
        ledger_error = str(exc)

    return Completion(
        data=answer,
        cached=False,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_usd=cost,
        purpose=purpose,
        prompt_version=prompt_version,
        model=chosen,
        reasoning_effort=effort,
        fingerprint=(str(body["system_fingerprint"]) if body.get("system_fingerprint") else None),
        ledger_error=ledger_error,
        latency_ms=latency_ms,
    )


def model_configured() -> bool:
    """True when a model has been chosen for this environment (PRD 7)."""
    return bool((get_settings().openrouter_model or "").strip())
