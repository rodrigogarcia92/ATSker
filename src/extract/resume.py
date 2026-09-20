"""Résumé extraction (PRD F2.3): one structured-output call, vocabulary-constrained.

The model is a parser here, not an editor: it turns an uploaded document into the
draft's fields, and every skill it names must already exist in the shared
vocabulary. Certification classification is *not* asked of the model — the prompt
collects one array of education-or-certification entries, `ingest.draft` decides
with deterministic rules first, and only the leftovers follow the model's own
`kind` proposal, flagged for the review screen.
"""

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db import short_session
from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import RESUME_EXTRACTION
from src.models import Skill

PURPOSE = "resume_extract"

# One retry for a schema violation, like the other extraction calls.
RETRIES = 1

CredentialKind = Literal["education", "certification", "unsure"]


class ExtractedCredential(BaseModel):
    """One line under an education or certification heading, as printed.

    `kind` is the model's own reading and is only trusted when no deterministic
    signal fires; `fill` fields stay None when the document does not state them.
    """

    kind: CredentialKind = "unsure"
    name: str = ""
    issuer: str = ""
    field: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    issued_date: str | None = None
    expiry_date: str | None = None
    credential_id: str | None = None
    credential_url: str | None = None


class ExtractedRole(BaseModel):
    employer: str = ""
    title: str = ""
    start_date: str | None = None
    end_date: str | None = None
    bullets: list[str] = Field(default_factory=list)


class ResumeExtraction(BaseModel):
    language: str = "es"
    headline: str = ""
    summary: str = ""
    roles: list[ExtractedRole] = Field(default_factory=list)
    credentials: list[ExtractedCredential] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


def vocabulary_rows(session: Session) -> list[str]:
    """`canonical — kind` lines, the block the prompt constrains skills to."""
    skills = session.scalars(select(Skill).order_by(Skill.canonical))
    return [f"{skill.canonical} — {skill.kind}" for skill in skills]


def extract_resume(
    session: Session,
    text: str,
    *,
    known_names: list[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> tuple[ResumeExtraction, Completion]:
    """Return the parsed document and the call that produced it.

    The text arrives already normalised (`ingest.documents.normalize_document_text`)
    so that the same upload hashes to the same cache entry; contact details are
    redacted before anything leaves for the provider (PRD 10).
    """
    if not text.strip():
        raise ValueError("the document has no text to extract")

    # The prompt's vocabulary read is the function's own: the caller's transaction is
    # never opened or ended here (client.complete_json refuses to run inside one).
    with short_session(session) as reader:
        skills = vocabulary_rows(reader)
    system = RESUME_EXTRACTION.render_system(skills="\n".join(skills), languages="es, en")
    completion = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=RESUME_EXTRACTION.version,
        system=system,
        user=RESUME_EXTRACTION.render(text=redaction.redact(text, known_names=known_names)),
        schema=ResumeExtraction,
        model=model,
        retries=RETRIES,
        options=options,
    )
    return ResumeExtraction.model_validate(completion.data), completion
