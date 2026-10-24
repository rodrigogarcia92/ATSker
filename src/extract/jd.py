"""JD extraction (PRD F4.2): one call, native structured output, cached by content hash.

The model is a parser here, not a judge: it turns a posting into its fields and is
allowed to name skills only from the vocabulary it was handed. Everything it
proposes outside that vocabulary is moved to `raw_keywords` and logged as a
candidate — which is the only path by which the vocabulary grows.
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import short_session
from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import JD_EXTRACTION_V4
from src.jd import Seniority, StructuredJD, jd_hash, normalize_jd_text
from src.models import Skill
from src.normalize.text import fold
from src.vocabulary import log_unmapped

PURPOSE = "jd_extract"

# One retry for a schema violation (PRD F4.3's rule for the grading call, applied
# where a provider drops an enum or returns a string where a list belongs).
RETRIES = 1


class JDProposal(BaseModel):
    """What the model may return. `hard_requirements` are disqualifiers, not scores."""

    language: str = Field(default="es", description="ISO 639-1 code of the posting")
    title: str = Field(default="")
    seniority: Seniority = "unknown"
    years_required: float | None = None
    must_have: list[str] = Field(default_factory=list)
    nice_to_have: list[str] = Field(default_factory=list)
    raw_keywords: list[str] = Field(default_factory=list)
    # F5.5.2: at most eight, and a posting extracted before this field existed
    # still validates — the default is an empty list, never a failure.
    responsibilities: list[str] = Field(default_factory=list, max_length=8)
    hard_requirements: list[str] = Field(default_factory=list)
    location_policy: str | None = None


def _split_known(proposals: Sequence[str], vocabulary: set[str]) -> tuple[list[str], list[str]]:
    """Partition proposed skills into vocabulary canonicals and everything else."""
    known: list[str] = []
    unknown: list[str] = []
    for value in proposals:
        cleaned = fold(str(value))
        if not cleaned:
            continue
        if cleaned in vocabulary:
            if cleaned not in known:
                known.append(cleaned)
        elif cleaned not in unknown:
            unknown.append(cleaned)
    return known, unknown


def vocabulary_canonicals(session: Session) -> list[str]:
    return list(session.scalars(select(Skill.canonical).order_by(Skill.canonical)))


def extract_jd(
    session: Session, text: str, *, model: str | None = None, options: CallOptions | None = None
) -> tuple[StructuredJD, Completion]:
    """Return the structured posting and the call that produced it.

    The call carries whether it was served from the cache and what it cost, which
    is what the analysis records (PRD 7).
    """
    normalized = normalize_jd_text(text)
    if not normalized:
        raise ValueError("the job description is empty")

    # The vocabulary read is the function's own: the caller's transaction is never
    # opened or ended here (client.complete_json refuses to run inside one).
    with short_session(session) as reader:
        canonicals = vocabulary_canonicals(reader)
    system = JD_EXTRACTION_V4.render_system(skills="\n".join(canonicals), languages="es, en")
    completion = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=JD_EXTRACTION_V4.version,
        system=system,
        user=JD_EXTRACTION_V4.render(text=redaction.redact(normalized)),
        schema=JDProposal,
        model=model,
        retries=RETRIES,
        options=options,
    )
    proposal = JDProposal.model_validate(completion.data)

    vocabulary = {fold(name) for name in canonicals}
    must_have, unknown_must = _split_known(proposal.must_have, vocabulary)
    nice_to_have, unknown_nice = _split_known(proposal.nice_to_have, vocabulary)
    log_unmapped(session, [*unknown_must, *unknown_nice])

    raw_keywords: list[str] = []
    for value in [*proposal.raw_keywords, *unknown_must, *unknown_nice]:
        cleaned = fold(str(value))
        if cleaned and cleaned not in raw_keywords:
            raw_keywords.append(cleaned)

    jd = StructuredJD(
        source_hash=jd_hash(text),
        language=fold(proposal.language) or "es",
        title=proposal.title.strip(),
        seniority=proposal.seniority,
        years_required=proposal.years_required,
        must_have=must_have,
        nice_to_have=nice_to_have,
        raw_keywords=raw_keywords,
        responsibilities=[
            str(value).strip() for value in proposal.responsibilities if str(value).strip()
        ],
        hard_requirements=[
            fold(str(value)) for value in proposal.hard_requirements if str(value).strip()
        ],
        location_policy=proposal.location_policy,
    )
    return jd, completion
