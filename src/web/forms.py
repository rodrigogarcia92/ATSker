"""Form value parsing.

Dates arrive as an empty string when a field is cleared, and multi-value fields
arrive as text; both are normalised here so the data-access layer only ever sees
clean types.
"""

import uuid
from datetime import date


def parse_date(value: str | None) -> date | None:
    if not value or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def parse_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def parse_list(value: str | None) -> list[str]:
    """Comma- or newline-separated values, in order, without duplicates."""
    if not value:
        return []
    parts = [part.strip() for chunk in value.replace("\n", ",").split(",") for part in [chunk]]
    seen: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.append(part)
    return seen


def parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def parse_uuids(values: list[str] | None) -> list[uuid.UUID]:
    return [parsed for value in (values or []) if (parsed := parse_uuid(value)) is not None]


def is_checked(value: str | None) -> bool:
    return (value or "").lower() in {"on", "true", "1", "yes"}
