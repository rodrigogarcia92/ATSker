"""Gap interpretation (PRD F6, F6.1): one call that explains detection's gaps.

The model discovers nothing. The ordered gap list goes in and comes back in the same
order, requirement text unchanged, each gap carrying a blocking flag and one line of
interpretation; anything else — a reordered list, a dropped gap, a gap nobody
supplied — is a schema violation: one retry, then a loud failure (the same rule F5.4
applies to a citation with a null bullet id).

Alongside the gaps the call returns exactly one warning (the standing risks that
bite on this posting plus anything posting-specific, with a suggested handling) and
one statement of what was not found in the user's data — never filler. When no
stories are available the answer says that, rather than implying none were relevant.

`src.extract` may not import `src.score` (PRD 5.1), so the input row here mirrors
`score.gaps.Gap` instead of importing it; `analysis.py` is where the two meet.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.extract import redaction
from src.extract.client import CallOptions, Completion, complete_json
from src.extract.prompts import GAP_INTERPRETATION, summarize_rows
from src.jd import StructuredJD
from src.models import Story

PURPOSE = "gap_interpret"

# One retry for a schema violation, like the other extraction calls.
RETRIES = 1


@dataclass(frozen=True)
class GapInput:
    """One gap as the call sees it: what detection produced, minus the bullet id."""

    requirement: str
    level: int
    must_have: bool
    bullet_text: str | None = None


class GapNote(BaseModel):
    requirement: str = ""
    blocking: bool = False
    interpretation: str = ""


class GapWarning(BaseModel):
    text: str = ""
    handling: str = ""


class GapInterpretation(BaseModel):
    gaps: list[GapNote] = Field(default_factory=list)
    warning: GapWarning = Field(default_factory=GapWarning)
    not_found: str = ""


class GapViolation(RuntimeError):
    """The model's answer cannot be trusted: it reordered, dropped or invented a gap."""


@dataclass(frozen=True)
class GapReading:
    notes: tuple[GapNote, ...]
    warning: GapWarning
    not_found: str
    calls: tuple[Completion, ...] = ()

    @property
    def cached(self) -> bool:
        """True when the last call was served from the cache; nothing was spent."""
        return bool(self.calls) and self.calls[-1].cached


def _validate(answer: GapInterpretation, expected: Sequence[GapInput]) -> tuple[GapNote, ...]:
    if len(answer.gaps) != len(expected):
        raise GapViolation(
            f"expected {len(expected)} gap notes, got {len(answer.gaps)}: the model may "
            "not add a gap or drop one"
        )
    for index, (note, gap) in enumerate(zip(answer.gaps, expected, strict=True)):
        if note.requirement != gap.requirement:
            raise GapViolation(
                f"gap {index} is {note.requirement!r}, not the supplied {gap.requirement!r}: "
                "the model may not reorder or rewrite a gap"
            )
    return tuple(answer.gaps)


def interpret_gaps(
    session: Session,
    gaps: Sequence[GapInput],
    jd: StructuredJD,
    *,
    standing_risks: Sequence[str] = (),
    stories: Sequence[Story] = (),
    language: str = "es",
    known_names: Sequence[str] | None = None,
    model: str | None = None,
    options: CallOptions | None = None,
) -> GapReading:
    """One call over the whole gap list, cached by content hash (PRD F6).

    Every attempt is kept, including a retry: an analysis's cost is the sum of what
    it actually spent, and a retried call was spent twice. `stories` is the
    profile's story table read whole — they are the person's own material, and when
    the table is empty the prompt says so out loud instead of leaving the model to
    imply a search happened.
    """
    names = list(known_names or [])
    gap_rows = [
        "\t".join(
            (
                str(index),
                f"L{gap.level}",
                "must" if gap.must_have else "nice",
                gap.requirement,
                redaction.redact(gap.bullet_text, known_names=names or None)
                if gap.bullet_text
                else "",
            )
        )
        for index, gap in enumerate(gaps)
    ]
    risk_rows = [redaction.redact(risk, known_names=names or None) for risk in standing_risks]
    story_rows = [
        f"{story.title}\t{redaction.redact(story.body, known_names=names or None)}"
        + (f"\t[{', '.join(story.tags)}]" if story.tags else "")
        for story in stories
    ]
    prompt = GAP_INTERPRETATION.render(
        gaps=summarize_rows(gap_rows),
        posting=(
            f"title: {jd.title}\nseniority: {jd.seniority}\n"
            f"years asked: {jd.years_required if jd.years_required is not None else '(none)'}\n"
            f"must-have: {', '.join(jd.must_have) or '(none)'}\n"
            f"nice-to-have: {', '.join(jd.nice_to_have) or '(none)'}\n"
            f"keywords: {', '.join(jd.raw_keywords) or '(none)'}\n"
            f"hard requirements: {', '.join(jd.hard_requirements) or '(none)'}\n"
            f"location policy: {jd.location_policy or '(none)'}"
        ),
        risks=summarize_rows(risk_rows, empty="(none recorded)"),
        stories=summarize_rows(story_rows, empty="(none available)"),
        lang=language,
    )
    attempts: list[Completion] = []

    # One retry: the client covers a schema violation, this loop covers the rule that
    # the model explains the gaps it was given and never grows the list.
    for attempt in range(2):
        completion = complete_json(
            session,
            purpose=PURPOSE,
            prompt_version=GAP_INTERPRETATION.version,
            system=GAP_INTERPRETATION.render_system(),
            user=prompt
            if attempt == 0
            else f"{prompt}\n\nYour previous answer was unusable: return exactly one note "
            "per gap, in the order given, with each requirement text copied unchanged.",
            schema=GapInterpretation,
            model=model,
            retries=RETRIES,
            options=options,
        )
        attempts.append(completion)
        answer = GapInterpretation.model_validate(completion.data)
        try:
            notes = _validate(answer, gaps)
        except GapViolation:
            if attempt == 0:
                continue
            raise
        return GapReading(
            notes=notes,
            warning=answer.warning,
            not_found=answer.not_found,
            calls=tuple(attempts),
        )

    raise GapViolation("gap interpretation failed after a retry")  # pragma: no cover
