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
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.config import get_settings
from src.models import LlmCall

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_SECONDS = 60.0

SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
    fingerprint: str | None = None
    ledger_error: str | None = None


def _post(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    """Single choke point for the network, so tests can replace it."""
    response = httpx.post(
        ENDPOINT,
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _schema_for(schema: type[BaseModel]) -> dict[str, Any]:
    return {
        "name": schema.__name__,
        "strict": True,
        "schema": schema.model_json_schema(),
    }


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

    attempt = 0
    while True:
        try:
            body = _post(payload, settings.openrouter_api_key.get_secret_value())
        except httpx.HTTPError as exc:
            # A transport or status failure spends nothing and caches nothing, but
            # the caller still needs to name it rather than fail as an unknown 500.
            raise ProviderUnavailable(str(exc)) from exc
        message = body["choices"][0]["message"]["content"]
        try:
            parsed = schema.model_validate(json.loads(message))
        except (json.JSONDecodeError, ValidationError) as exc:
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

    usage = body.get("usage") or {}
    cost = Decimal(str(usage.get("cost") or 0))
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
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
        fingerprint=(str(body["system_fingerprint"]) if body.get("system_fingerprint") else None),
        ledger_error=ledger_error,
    )


def model_configured() -> bool:
    """True when a model has been chosen for this environment (PRD 7)."""
    return bool((get_settings().openrouter_model or "").strip())
