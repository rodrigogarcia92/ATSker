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


@dataclass(frozen=True)
class Completion:
    data: dict[str, Any]
    cached: bool
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


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
) -> Completion:
    settings = get_settings()
    chosen = model or (settings.openrouter_model or "").strip()
    if not chosen:
        raise NoModelConfigured("OPENROUTER_MODEL is not set")
    if settings.openrouter_api_key is None:
        raise NoModelConfigured("OPENROUTER_API_KEY is not set")

    digest = _input_hash(purpose, prompt_version, chosen, system, user)
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

    attempt = 0
    while True:
        body = _post(payload, settings.openrouter_api_key.get_secret_value())
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
    )
