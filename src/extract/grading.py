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

A fourth rule is added rather than trusted (F5.5.2): the *family backstop* runs
after `_enforce`, and fills in an `equivalent` the model left at 0 when the family
data already proves one. It is the same one hop, in the other direction — the
posting names Power BI and the CV shows Tableau, both in `bi_tool` — so a
requirement the vocabulary puts in a family may be credited from a sibling that is
evidenced here. It only ever raises a credit (`level/3 × equivalent` must beat the
row's own `level/3 × basis`), never lowers one, and it names the sibling it used.
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
from src.extract.prompts import EVIDENCE_GRADING_V4, summarize_rows
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
    # F5.5.2: the level and basis came from the family data rather than from the
    # model, so the report can say which rows a sibling stood in for.
    inferred: bool = False


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


def _family_table(families: Mapping[str, str | None]) -> str:
    """`family: canonical, canonical, …`, one line per non-null family (F5.5.2).

    Rendered from the database rather than written into the prompt: which skills
    are equivalents is operator-reviewed data, so the model is told exactly which
    ones exist and the backstop below grants only those.
    """
    grouped: dict[str, list[str]] = {}
    for canonical, family in families.items():
        if family:
            grouped.setdefault(family, []).append(canonical)
    return "\n".join(
        f"{family}: {', '.join(sorted(members))}" for family, members in sorted(grouped.items())
    )


def _family_equivalent(
    index: int,
    canonical: str | None,
    *,
    resolved: Sequence[str | None],
    enforced: Sequence[tuple[int, str, bool, bool]],
    rows: Sequence[GradeRow],
    bullets: Sequence[Bullet],
    families: Mapping[str, str | None],
    basis_credit: Mapping[str, float],
    language: str,
) -> tuple[int, str, str | None, str] | None:
    """F5.5.2's backstop: (level, source, evidence_id, transfer_reason), or None.

    Two candidates, in order. A is another requirement of this posting in the same
    family, itself directly evidenced at level 2 or better — its level, source and
    citation travel over, which is why a `direct` row never chains into an
    `equivalent` one. B is the first supplied bullet whose own skill chips name a
    family sibling, worth level 2 as a described task. Either is applied only when
    its credit strictly beats the row's own, so a directly evidenced level 3 is
    never lowered to an equivalent.
    """
    family = families.get(canonical) if canonical else None
    if not family:
        return None

    def is_sibling(candidate: str) -> bool:
        return candidate != canonical and families.get(candidate) == family

    found: tuple[int, str, str | None, str] | None = None
    for other, (other_canonical, (other_level, other_basis, _, _)) in enumerate(
        zip(resolved, enforced, strict=True)
    ):
        if other == index or not other_canonical or not is_sibling(other_canonical):
            continue
        if other_level >= 2 and other_basis == "direct":
            found = (other_level, rows[other].source, rows[other].evidence_id, other_canonical)
            break
    if found is None:
        for bullet in bullets:
            sibling = next((skill for skill in bullet.skills if is_sibling(skill)), None)
            if sibling is not None:
                found = (2, "bullet", str(bullet.id), sibling)
                break
    if found is None:
        return None

    level, _source, _evidence_id, sibling = found
    row_level, row_basis, _, _ = enforced[index]
    offered = level / MAX_LEVEL * basis_credit["equivalent"]
    current = row_level / MAX_LEVEL * basis_credit[row_basis]
    if offered <= current:
        return None
    reason = (
        f"misma familia ({family}) que {sibling}"
        if language == "es"
        else f"same family ({family}) as {sibling}"
    )
    return (level, found[1], found[2], reason)


def grade_evidence(
    session: Session,
    jd: StructuredJD,
    bullets: Sequence[Bullet],
    *,
    basis_credit: Mapping[str, float],
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

    `basis_credit` is the caller's weight set (F5.5.1), never imported here: what
    a basis is worth is scoring configuration, and `extract/` may not depend on
    `score/` (PRD 5.1). The family backstop needs it to decide whether a sibling
    would actually count for more than the row already does.
    """
    requirements = requirements_of(jd)
    if not requirements:
        return EvidenceReport(levels=(), note="")

    # The vocabulary is shared data, not the caller's unit of work: read it on a
    # session of its own so the family check cannot hold the caller's transaction
    # across the provider call. It is read first because the family table is part
    # of the prompt (F5.5.2), and the table and the backstop must see the same rows.
    with Session(bind=session.get_bind()) as reader:
        aliases = alias_map(reader)
        families = {skill.canonical: skill.family for skill in reader.scalars(select(Skill))}

    numbered = "\n".join(f"{index}\t{value}" for index, (value, _) in enumerate(requirements))
    names = list(known_names or [])
    texts = {
        str(bullet.id): redaction.redact(bullet_text(bullet, language), known_names=names or None)
        for bullet in bullets
    }
    supplied = summarize_rows([f"{bullet_id}\t{text}" for bullet_id, text in texts.items()])
    allowed_ids = set(texts)
    prompt = EVIDENCE_GRADING_V4.render(
        requirements=numbered,
        bullets=supplied,
        summary=summarize_rows(
            [redaction.redact(summary_text, known_names=names or None)] if summary_text else []
        ),
        skills=summarize_rows([skills_text] if skills_text else []),
        lang=language,
    )
    system = EVIDENCE_GRADING_V4.render_system(families=_family_table(families))

    attempts: list[Completion] = []

    # One retry: the client covers a schema violation, this loop covers a citation one.
    for attempt in range(2):
        completion = complete_json(
            session,
            purpose=PURPOSE,
            prompt_version=EVIDENCE_GRADING_V4.version,
            system=system,
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

        # `_enforce` first, for every row, and only then the family backstop:
        # candidate A reads the other rows as the rules left them, so one row can
        # never be credited from a sibling that a later row would change.
        cited: str | None
        enforced: list[tuple[int, str, bool, bool]] = []
        for (requirement, _), row in zip(requirements, rows, strict=True):
            cited = texts.get(row.evidence_id or "") if row.source == "bullet" else None
            if row.source == "summary":
                cited = summary_text
            elif row.source == "skills_list":
                cited = skills_text
            enforced.append(
                _enforce(row, requirement, cited, aliases=aliases, families=families)
            )

        resolved = [aliases.get(fold(requirement)) for requirement, _ in requirements]
        levels: list[EvidenceLevel] = []
        for index, ((requirement, must_have), row) in enumerate(
            zip(requirements, rows, strict=True)
        ):
            level, basis, clamped, downgraded = enforced[index]
            source, evidence_id, transfer_reason = row.source, row.evidence_id, row.transfer_reason
            inferred = False
            replacement = _family_equivalent(
                index,
                resolved[index],
                resolved=resolved,
                enforced=enforced,
                rows=rows,
                bullets=bullets,
                families=families,
                basis_credit=basis_credit,
                language=language,
            )
            if replacement is not None:
                level, source, evidence_id, transfer_reason = replacement
                basis, inferred = "equivalent", True
            levels.append(
                EvidenceLevel(
                    requirement=requirement,
                    level=level,
                    must_have=must_have,
                    basis=basis,
                    source=source,
                    evidence_id=evidence_id,
                    transfer_reason=transfer_reason,
                    clamped=clamped,
                    downgraded=downgraded,
                    inferred=inferred,
                )
            )
        return EvidenceReport(levels=tuple(levels), note=grading.note, calls=tuple(attempts))

    raise CitationViolation("grading failed after a retry")  # pragma: no cover - loop returns
