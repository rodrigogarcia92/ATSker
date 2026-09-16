"""The structured job posting (PRD F4.2).

`extract/` produces this shape from raw text; `score/` consumes it. Defining it
here keeps the two ends from importing each other.
"""

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field

Seniority = Literal["intern", "junior", "mid", "senior", "lead", "principal", "unknown"]

# The rungs a title can sit on, weakest first. F4.4's title sub-score penalises a
# mismatch of one rung by 0.2 and two or more by 0.5.
SENIORITY_LADDER: tuple[Seniority, ...] = (
    "intern",
    "junior",
    "mid",
    "senior",
    "lead",
    "principal",
)

_WHITESPACE = re.compile(r"\s+")


class StructuredJD(BaseModel):
    """One analysed posting. Every field is either present or explicitly null."""

    source_hash: str = ""
    language: str = "es"
    title: str = ""
    seniority: Seniority = "unknown"
    years_required: float | None = None
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)
    hard_requirements: list[str] = Field(default_factory=list)
    location_policy: str | None = None


def normalize_jd_text(text: str) -> str:
    """Collapse what does not change meaning, so equal postings hash equal.

    Accents are deliberately kept: this text is also what a model reads, and
    stripping them would change the Spanish it sees.
    """
    unified = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return _WHITESPACE.sub(" ", unified).strip()


def jd_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(normalize_jd_text(text).encode("utf-8")).hexdigest()


def seniority_rung(value: str | None) -> int | None:
    """Position on the ladder, or None when the value is not a rung."""
    if not value:
        return None
    try:
        return SENIORITY_LADDER.index(value)  # type: ignore[arg-type]
    except ValueError:
        return None
