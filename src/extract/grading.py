"""Evidence grading (PRD F4.3): the only runtime model call that affects the score.

Lexical matching cannot tell a skill that is listed from a skill that was used, and
that distinction is what a human reader responds to — so the model is asked for one
ordinal per requirement with a citation, and nothing else.

A level above zero without a citation is a schema violation: one retry, then a loud
failure. The citation must also be an id that was actually supplied, or the model
would be inventing provenance, which is the one thing this project exists to avoid.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.extract import redaction
from src.extract.client import complete_json
from src.extract.prompts import EVIDENCE_GRADING, summarize_rows
from src.jd import StructuredJD
from src.models import Bullet

PURPOSE = "evidence_grade"
MAX_LEVEL = 3


class GradeRow(BaseModel):
    index: int = Field(description="0-based index of the requirement being graded")
    level: int = Field(ge=0, le=MAX_LEVEL)
    bullet_id: str | None = None


class EvidenceGrading(BaseModel):
    grades: list[GradeRow] = Field(default_factory=list)
    note: str = ""


class CitationViolation(RuntimeError):
    """The model's answer cannot be trusted: missing coverage, or provenance invented."""


@dataclass(frozen=True)
class EvidenceLevel:
    requirement: str
    level: int
    bullet_id: str | None
    must_have: bool


@dataclass(frozen=True)
class EvidenceReport:
    levels: tuple[EvidenceLevel, ...]
    note: str
    cached: bool


def requirements_of(jd: StructuredJD) -> list[tuple[str, bool]]:
    """Must-haves first, then nice-to-haves, each with its weight class."""
    return [(value, True) for value in jd.must_have] + [(value, False) for value in jd.nice_to_have]


def _validate(
    grading: EvidenceGrading,
    requirements: Sequence[tuple[str, bool]],
    allowed_ids: set[str],
) -> tuple[EvidenceLevel, ...]:
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

    levels: list[EvidenceLevel] = []
    for index, (requirement, must_have) in enumerate(requirements):
        row = by_index[index]
        if row.level > 0 and not row.bullet_id:
            raise CitationViolation(f"level {row.level} for {requirement!r} without a citation")
        if row.level == 0 and row.bullet_id:
            raise CitationViolation(f"level 0 for {requirement!r} cites a bullet")
        if row.bullet_id and row.bullet_id not in allowed_ids:
            raise CitationViolation(f"bullet {row.bullet_id!r} was never supplied")
        levels.append(EvidenceLevel(requirement, row.level, row.bullet_id, must_have))
    return tuple(levels)


def grade_evidence(
    session: Session,
    jd: StructuredJD,
    bullets: Sequence[Bullet],
    *,
    language: str = "es",
    model: str | None = None,
) -> EvidenceReport:
    """One call covering every requirement, cached by content hash (PRD F4.3)."""
    requirements = requirements_of(jd)
    if not requirements:
        return EvidenceReport(levels=(), note="", cached=False)

    numbered = "\n".join(f"{index}\t{value}" for index, (value, _) in enumerate(requirements))
    supplied = summarize_rows(
        [
            f"{bullet.id}\t{redaction.redact(bullet.text_es or bullet.text_en or '')}"
            for bullet in bullets
        ]
    )
    allowed_ids = {str(bullet.id) for bullet in bullets}
    prompt = EVIDENCE_GRADING.render(requirements=numbered, bullets=supplied, lang=language)

    # One retry: the client covers a schema violation, this loop covers a citation one.
    for attempt in range(2):
        completion = complete_json(
            session,
            purpose=PURPOSE,
            prompt_version=EVIDENCE_GRADING.version,
            system=EVIDENCE_GRADING.system,
            user=prompt
            if attempt == 0
            else f"{prompt}\n\nYour previous answer was unusable: cite only supplied "
            "bullet ids, and return exactly one grade per requirement index.",
            schema=EvidenceGrading,
            model=model,
        )
        grading = EvidenceGrading.model_validate(completion.data)
        try:
            levels = _validate(grading, requirements, allowed_ids)
        except CitationViolation:
            if attempt == 0:
                continue
            raise
        return EvidenceReport(levels=levels, note=grading.note, cached=completion.cached)

    raise CitationViolation("grading failed after a retry")  # pragma: no cover - loop returns
