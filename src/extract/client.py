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
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import LlmCall

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Payload keys the client omits for a given model (PRD §7): data, not code, so a model
# that refuses one — a reasoning model that rejects `temperature` with a 400 — is one
# line here rather than a branch. It starts empty on purpose: nobody guesses which models
# refuse what, and `model_selection.verify_prices` prints the entry to add.
MODEL_PARAMS_PATH = Path(__file__).with_name("model_params.json")
# The request is meaningless without these, so a model cannot be configured to lose them.
_NEVER_OMITTED = frozenset({"model", "messages"})
# The default `Settings.openrouter_timeout_seconds` starts from, kept importable so
# `fixtures/golden/probe_model.py` can measure against the app's own budget.
TIMEOUT_SECONDS = 60.0

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class ModelParamsError(RuntimeError):
    """`model_params.json` is unreadable or not a map of model id to payload keys."""


def load_model_params(path: Path = MODEL_PARAMS_PATH) -> dict[str, frozenset[str]]:
    """Read the per-model omissions, or fail naming the file and what is wrong with it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelParamsError(f"{path.name} cannot be read as JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ModelParamsError(
            f'{path.name} must be an object mapping a model id to a list of payload keys, e.g. '
            '{"openai/gpt-6.1-sol": ["temperature"]}'
        )
    params: dict[str, frozenset[str]] = {}
    for model, keys in raw.items():
        if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):
            raise ModelParamsError(f"{path.name}: {model!r} must map to a list of payload keys")
        forbidden = sorted(_NEVER_OMITTED & set(keys))
        if forbidden:
            raise ModelParamsError(
                f"{path.name}: {model!r} cannot omit {', '.join(forbidden)}; the request needs it"
            )
        params[model] = frozenset(keys)
    return params


# Read once, when the client is first imported: a malformed file stops the app at
# startup with the file's name, never on the first paid call.
OMIT_BY_MODEL: dict[str, frozenset[str]] = load_model_params()


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


def _write_ledger(
    session: Session,
    *,
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
) -> None:
    """Write the paid call's row on the client's own connection, with one retry.

    The row is also the cache entry (decision 21), so the retry is not only about
    the record: it is what stops the next identical call from paying again. A fresh
    connection cannot be the one the database killed while the provider worked.

    `degenerate` is the caller's verdict on its own answer (F2.3.1). The row is
    written either way — the call was paid for — and the flag is what excludes it
    from the cache lookup.
    """
    error: SQLAlchemyError | None = None
    for _ in range(2):
        try:
            with _client_session(session) as ledger:
                ledger.add(
                    LlmCall(
                        purpose=purpose,
                        prompt_version=prompt_version,
                        model=model,
                        input_hash=input_hash,
                        response_json=response_json,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost_usd=cost_usd,
                        degenerate=degenerate,
                        profile_id=profile_id,
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
    purpose: str,
    prompt_version: str,
    model: str,
    input_hash: str,
    error: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: Decimal,
    profile_id: uuid.UUID | None,
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
        )
    except LedgerWriteError:
        pass


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

    # Left alone, the provider runs its own default effort — high, medium and max
    # across the current candidates — which is a cost and latency variable nobody
    # chose. The setting pins the lowest advertised effort; an explicit option wins.
    effort = opts.reasoning_effort or settings.openrouter_reasoning_effort or None

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
        return Completion(
            data=cached.response_json,
            cached=True,
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=Decimal("0"),
            purpose=purpose,
            prompt_version=prompt_version,
            model=chosen,
            reasoning_effort=effort,
        )

    payload: dict[str, Any] = {
        "model": chosen,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_schema", "json_schema": _schema_for(schema)},
        "usage": {"include": True},
    }
    if opts.seed is not None:
        payload["seed"] = opts.seed
    if effort is not None:
        payload["reasoning"] = {"effort": effort}
    for omitted in OMIT_BY_MODEL.get(chosen, ()):
        payload.pop(omitted, None)

    attempt = 0
    while True:
        try:
            body = _post(payload, settings.openrouter_api_key.get_secret_value())
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
                purpose=purpose,
                prompt_version=prompt_version,
                model=chosen,
                input_hash=digest,
                error=str(exc),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                profile_id=opts.profile_id,
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
    )


def model_configured() -> bool:
    """True when a model has been chosen for this environment (PRD 7)."""
    return bool((get_settings().openrouter_model or "").strip())
