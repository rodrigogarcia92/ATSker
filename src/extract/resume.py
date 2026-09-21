"""Résumé extraction (PRD F2.3): one structured-output call, vocabulary-constrained.

The model is a parser here, not an editor: it turns an uploaded document into the
draft's fields, and every skill it names must already exist in the shared
vocabulary. Certification classification is *not* asked of the model — the prompt
collects one array of education-or-certification entries, `ingest.draft` decides
with deterministic rules first, and only the leftovers follow the model's own
`kind` proposal, flagged for the review screen.
"""

from dataclasses import replace
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

# Below this many characters of source text, an empty answer is plausible — a
# near-empty document legitimately extracts to nothing, and "this document has no
# text" is the message that fits. At or above it, an answer with no roles, no
# credentials and no skills is a failed extraction however well-formed it is: the
# observed defect was 6,793 characters in, 9 completion tokens out (F2.3.1). Two
# hundred characters is a couple of lines of prose — far below anything with a job
# to parse, far above a document that has no content to lose.
MIN_SUBSTANTIAL_CHARS = 200

CredentialKind = Literal["education", "certification", "unsure"]


class EmptyExtraction(RuntimeError):
    """The document had text and the model returned nothing (F2.3.1).

    Distinct from `ProviderUnavailable` (nothing was paid, nothing was learned) and
    from `StructuredOutputError` (the answer did not fit the schema): here the answer
    fitted the schema and said nothing. The character count travels with the error so
    the screen can report what went in.
    """

    def __init__(self, characters: int) -> None:
        super().__init__(
            f"{characters} characters of source text produced an empty extraction"
        )
        self.characters = characters


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


def is_degenerate(extraction: ResumeExtraction) -> bool:
    """True when the answer carries no career content at all (F2.3.1).

    Schema-valid and empty at the same time: every field on `ResumeExtraction` has a
    default, so `{}` validates. The headline and summary are deliberately not
    evidence of success — a model that returns only a headline has still failed to
    parse the document, and a draft built from it would be an empty review screen
    again.
    """
    return not extraction.roles and not extraction.credentials and not extraction.skills


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

    A degenerate answer gets one more attempt, uncached, and if that is degenerate
    too the extraction is reported as failed rather than handed to the review screen
    as an empty draft (F2.3.1). Both attempts are marked in the ledger, so neither
    can be served back by the cache.
    """
    if not text.strip():
        raise ValueError("the document has no text to extract")

    # The prompt's vocabulary read is the function's own: the caller's transaction is
    # never opened or ended here (client.complete_json refuses to run inside one).
    with short_session(session) as reader:
        skills = vocabulary_rows(reader)
    system = RESUME_EXTRACTION.render_system(skills="\n".join(skills), languages="es, en")
    source = redaction.redact(text, known_names=known_names)
    user = RESUME_EXTRACTION.render(text=source)
    # The caller's own verdict on its own answers: the count is of the text the call
    # was made over, which is the same text the content hash covers.
    substantial = len(source) >= MIN_SUBSTANTIAL_CHARS
    opts = options or CallOptions()
    if substantial:
        opts = replace(opts, degenerate=lambda answer: is_degenerate(_validated(answer)))

    completion = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=RESUME_EXTRACTION.version,
        system=system,
        user=user,
        schema=ResumeExtraction,
        model=model,
        retries=RETRIES,
        options=opts,
    )
    extraction = ResumeExtraction.model_validate(completion.data)
    if not substantial or not is_degenerate(extraction):
        return extraction, completion

    # One more attempt, fresh: the cached answer is the degenerate one just returned,
    # so retrying through the cache would only serve it again.
    retry = complete_json(
        session,
        purpose=PURPOSE,
        prompt_version=RESUME_EXTRACTION.version,
        system=system,
        user=user,
        schema=ResumeExtraction,
        model=model,
        retries=RETRIES,
        options=replace(opts, bypass_cache=True),
    )
    extraction = ResumeExtraction.model_validate(retry.data)
    if is_degenerate(extraction):
        raise EmptyExtraction(len(source))
    # Both calls were paid for; report a ledger gap from either one.
    return extraction, replace(retry, ledger_error=completion.ledger_error or retry.ledger_error)


def _validated(answer: dict) -> ResumeExtraction:
    """The parsed answer the client already schema-checked, as a model."""
    return ResumeExtraction.model_validate(answer)
