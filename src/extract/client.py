"""OpenRouter chat completions: structured output, temperature 0, cached by hash.

Cost and token counts land in `llm_calls` on every uncached call, which is where
PRD 7's cost instrumentation comes from. The stored response doubles as the cache,
so a repeat of the same purpose, prompt version, model and input makes no network
call and returns byte-identical output.
"""

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
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


@dataclass(frozen=True)
class CallOptions:
    """How a caller wants its model calls made.

    Defaults are production behaviour: the content-hash cache is read, temperature
    is 0, and nothing else is pinned. The model-selection experiment turns the
    cache off so that repeated runs measure the judge rather than the cache, and
    pins a seed and a reasoning effort so the repeats are as comparable as the
    provider allows.
    """

    bypass_cache: bool = False
    seed: int | None = None
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Completion:
    """One call site's answer, and what it cost.

    `purpose`, `prompt_version` and `model` travel with the answer so the caller
    can record the analysis's prompt versions and cost without re-deriving them.
    `fingerprint` is whatever the provider echoed to identify the backend
    (OpenRouter's `system_fingerprint`), which is how a caller can tell whether a
    seeded request was honoured or merely accepted.
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
    settings = get_settings()
    chosen = model or (settings.openrouter_model or "").strip()
    if not chosen:
        raise NoModelConfigured("OPENROUTER_MODEL is not set")
    if settings.openrouter_api_key is None:
        raise NoModelConfigured("OPENROUTER_API_KEY is not set")

    key = [purpose, prompt_version, chosen, system, user]
    if opts.seed is not None:
        key.append(f"seed={opts.seed}")
    if opts.reasoning_effort is not None:
        key.append(f"reasoning={opts.reasoning_effort}")
    digest = _input_hash(*key)

    cached = None
    if not opts.bypass_cache:
        cached = session.scalar(
            select(LlmCall).where(
                LlmCall.purpose == purpose,
                LlmCall.prompt_version == prompt_version,
                LlmCall.input_hash == digest,
            )
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
    if opts.reasoning_effort is not None:
        payload["reasoning"] = {"effort": opts.reasoning_effort}

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
    session.add(
        LlmCall(
            purpose=purpose,
            prompt_version=prompt_version,
            model=chosen,
            input_hash=digest,
            response_json=parsed.model_dump(mode="json"),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            cost_usd=cost,
        )
    )
    session.flush()

    return Completion(
        data=parsed.model_dump(mode="json"),
        cached=False,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        cost_usd=cost,
        purpose=purpose,
        prompt_version=prompt_version,
        model=chosen,
        fingerprint=(str(body["system_fingerprint"]) if body.get("system_fingerprint") else None),
    )


def model_configured() -> bool:
    """True when a model has been chosen for this environment (PRD 7)."""
    return bool((get_settings().openrouter_model or "").strip())
