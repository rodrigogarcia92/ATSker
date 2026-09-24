"""Evidence grading (PRD F5.4, F5.4.1): the only runtime model call that affects the score.

Lexical matching cannot tell a skill that is listed from a skill that was used, and
that distinction is what a human reader responds to — so the model is asked for one
ordinal per requirement with a citation and an evidence basis, and nothing else.

The whole track is read (F5.4.1): the bullets as before, plus the summary and the
skills list, each marked as not being a bullet. A level above zero must say which of
the three sources holds the evidence, and a bullet citation must name a supplied id
— inventing provenance is the one thing this project exists to avoid. A schema
violation is retried once and then fails loudly.

Three rules are enforced here, never trusted to the model (F5.4.1):

* the level-1 cap — evidence found only in the summary or the skills list is
  noted, not proven, so it is clamped to 1 and the report says it was clamped;
* the family check — `equivalent` is one hop and it is data: when the requirement
  and the cited skill resolve to canonicals, they must share a non-null
  `skills.family` (through the vocabulary's alias map, never string matching), or
  the basis is downgraded to `transferable` and the report says so. An equivalence
  the data cannot confirm is not granted the credit;
* the snapshot happens at the call site (analysis), from the same document text
  the model was shown, in the language it was shown in.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.bullets import bullet_text
from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import EVIDENCE_GRADING, summarize_rows
from src.jd import StructuredJD
from src.models import Bullet, Skill
from src.normalize.text import fold
from src.normalize.vocabulary import match_text
from src.vocabulary import alias_map

PURPOSE = "evidence_grade"
MAX_LEVEL = 3

Basis = Literal["direct", "equivalent", "transferable", "none"]
Source = Literal["bullet", "summary", "skills_list"]

# The non-bullet sources: a reader notes them, a described task proves them, so
# evidence found only here is graded 1 at most (F5.4.1's cap).
NOTED_SOURCES = frozenset({"summary", "skills_list"})


class GradeRow(BaseModel):
    index: int = Field(description="0-based index of the requirement being graded")
    level: int = Field(ge=0, le=MAX_LEVEL)
    basis: Basis = "none"
    source: Source | None = None
    evidence_id: str | None = None
    transfer_reason: str | None = None


class EvidenceGrading(BaseModel):
    grades: list[GradeRow] = Field(default_factory=list)
    note: str = ""


class CitationViolation(RuntimeError):
    """The model's answer cannot be trusted: missing coverage, or provenance invented."""


@dataclass(frozen=True)
class EvidenceLevel:
    requirement: str
    level: int
    must_have: bool
    basis: str
    source: str | None
    evidence_id: str | None
    transfer_reason: str | None
    clamped: bool = False
    downgraded: bool = False


@dataclass(frozen=True)
class EvidenceReport:
    levels: tuple[EvidenceLevel, ...]
    note: str
    calls: tuple[Completion, ...] = ()

    @property
    def cached(self) -> bool:
        """True when the last call was served from the cache; nothing was spent."""
        return bool(self.calls) and self.calls[-1].cached


def requirements_of(jd: StructuredJD) -> list[tuple[str, bool]]:
    """Must-haves first, then nice-to-haves, each with its weight class."""
    return [(value, True) for value in jd.must_have] + [(value, False) for value in jd.nice_to_have]


def _validate(
    grading: EvidenceGrading,
    requirements: Sequence[tuple[str, bool]],
    allowed_ids: set[str],
) -> list[GradeRow]:
    by_index: dict[int, GradeRow] = {}
    for row in grading.grades:
        if row.index in by_index:
            raise CitationViolation(f"requirement {row.index} was graded twice")
        if not 0 <= row.index < len(requirements):
            raise CitationViolation(f"requirement index {row.index} does not exist")
        by_index[row.index] = row

    if len(by_index) != len(requirements):
        missing = sorted(set(range(len(requirements))) - set(by_index))
        raise CitationViolation(f"no grade returned for requirements {missing}")

    rows: list[GradeRow] = []
    for index, (requirement, _) in enumerate(requirements):
        row = by_index[index]
        if row.level > 0 and not row.source:
            raise CitationViolation(f"level {row.level} for {requirement!r} without a source")
        if row.level > 0 and row.source == "bullet" and not row.evidence_id:
            raise CitationViolation(f"level {row.level} for {requirement!r} without a citation")
        if row.level == 0 and row.evidence_id:
            raise CitationViolation(f"level 0 for {requirement!r} cites evidence")
        if row.evidence_id and row.evidence_id not in allowed_ids:
            raise CitationViolation(f"bullet {row.evidence_id!r} was never supplied")
        if row.basis not in ("direct", "none") and not (
            row.transfer_reason or ""
        ).strip():
            raise CitationViolation(
                f"basis {row.basis!r} for {requirement!r} without a transfer_reason"
            )
        rows.append(row)
    return rows


def _enforce(
    row: GradeRow,
    requirement: str,
    cited_text: str | None,
    *,
    aliases: Mapping[str, str],
    families: Mapping[str, str | None],
) -> tuple[int, str, bool, bool]:
    """The two rules code enforces; returns level, basis, clamped, downgraded (F5.4.1)."""
    level, basis = row.level, row.basis
    clamped = False
    if row.source in NOTED_SOURCES and level > 1:
        level = 1
        clamped = True

    downgraded = False
    if basis == "equivalent":
        # Equivalence is data: the requirement and a cited skill must resolve to
        # canonicals that share a non-null family, or the credit is not granted.
        wanted = aliases.get(fold(requirement))
        cited = set(match_text(cited_text or "", aliases))
        confirmed = wanted is not None and any(
            families.get(skill) is not None and families.get(skill) == families.get(wanted)
            for skill in cited
        )
        if not confirmed:
            basis = "transferable"
            downgraded = True
    return level, basis, clamped, downgraded


def grade_evidence(
    session: Session,
    jd: StructuredJD,
    bullets: Sequence[Bullet],
    *,
    summary_text: str | None = None,
    skills_text: str | None = None,
    language: str = "es",
    model: str | None = None,
    known_names: Sequence[str] | None = None,
    options: CallOptions | None = None,
) -> EvidenceReport:
    """One call covering every requirement, cached by content hash (PRD F5.4).

    `summary_text` and `skills_text` are the track's other two sources (F5.4.1),
    each sent as its own clearly marked source that is not a bullet. Every attempt
    is kept, including a retry: an analysis's cost is the sum of what it actually
    spent, and a retried call was spent twice.
    """
    requirements = requirements_of(jd)
    if not requirements:
        return EvidenceReport(levels=(), note="")

    numbered = "\n".join(f"{index}\t{value}" for index, (value, _) in enumerate(requirements))
    names = list(known_names or [])
    texts = {
        str(bullet.id): redaction.redact(bullet_text(bullet, language), known_names=names or None)
        for bullet in bullets
    }
    supplied = summarize_rows([f"{bullet_id}\t{text}" for bullet_id, text in texts.items()])
    allowed_ids = set(texts)
    prompt = EVIDENCE_GRADING.render(
        requirements=numbered,
        bullets=supplied,
        summary=summarize_rows(
            [redaction.redact(summary_text, known_names=names or None)] if summary_text else []
        ),
        skills=summarize_rows([skills_text] if skills_text else []),
        lang=language,
    )

    # The vocabulary is shared data, not the caller's unit of work: read it on a
    # session of its own so the family check cannot hold the caller's transaction
    # across the provider call.
    with Session(bind=session.get_bind()) as reader:
        aliases = alias_map(reader)
        families = {skill.canonical: skill.family for skill in reader.scalars(select(Skill))}

    attempts: list[Completion] = []

    # One retry: the client covers a schema violation, this loop covers a citation one.
    for attempt in range(2):
        completion = complete_json(
            session,
            purpose=PURPOSE,
            prompt_version=EVIDENCE_GRADING.version,
            system=EVIDENCE_GRADING.render_system(),
            user=prompt
            if attempt == 0
            else f"{prompt}\n\nYour previous answer was unusable: cite only supplied "
            "bullet ids, return exactly one grade per requirement index, and give a "
            "source and — for a non-direct basis — a transfer_reason.",
            schema=EvidenceGrading,
            model=model,
            options=options,
        )
        attempts.append(completion)
        grading = EvidenceGrading.model_validate(completion.data)
        try:
            rows = _validate(grading, requirements, allowed_ids)
        except CitationViolation:
            if attempt == 0:
                continue
            raise

        levels: list[EvidenceLevel] = []
        for (requirement, must_have), row in zip(requirements, rows, strict=True):
            cited = texts.get(row.evidence_id or "") if row.source == "bullet" else None
            if row.source == "summary":
                cited = summary_text
            elif row.source == "skills_list":
                cited = skills_text
            level, basis, clamped, downgraded = _enforce(
                row, requirement, cited, aliases=aliases, families=families
            )
            levels.append(
                EvidenceLevel(
                    requirement=requirement,
                    level=level,
                    must_have=must_have,
                    basis=basis,
                    source=row.source,
                    evidence_id=row.evidence_id,
                    transfer_reason=row.transfer_reason,
                    clamped=clamped,
                    downgraded=downgraded,
                )
            )
        return EvidenceReport(levels=tuple(levels), note=grading.note, calls=tuple(attempts))

    raise CitationViolation("grading failed after a retry")  # pragma: no cover - loop returns
