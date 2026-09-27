"""Bullet pairing (PRD F4.2's translation import): which lines say the same thing.

The model's judgement is *meaning* only — do these two lines describe the same
work? Everything else is code: which roles are compared, that a pairing is
one-to-one, that an index names a line that was supplied, and which column of a
bullet the answer may fill. The citation rules are `grading.CitationViolation`'s,
reused rather than re-invented, because a model citing something it was not given
is the same failure here as it is there.

Cached by content hash like every other extraction call: reviewing the same
document against the same role twice costs nothing the second time.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from src.extract.client import CallOptions, Completion, complete_json
from src.extract.grading import CitationViolation
from src.extract.prompts import BULLET_PAIRING_V1

PURPOSE = "bullet_pairing"

# One retry, like every other citation-checked call: the client covers a schema
# violation, this module's loop covers a citation one.
RETRIES = 1


class PairRow(BaseModel):
    existing: int = Field(description="index in the first list")
    draft: int = Field(description="index in the second list")


class BulletPairing(BaseModel):
    pairs: list[PairRow] = Field(default_factory=list)


@dataclass(frozen=True)
class BulletPair:
    """One confirmed match: the line that exists, and the line that says it again."""

    existing: int
    draft: int


@dataclass(frozen=True)
class PairingReport:
    pairs: tuple[BulletPair, ...]
    calls: tuple[Completion, ...] = ()


def _validate(
    pairing: BulletPairing, existing_count: int, draft_count: int
) -> tuple[BulletPair, ...]:
    """One-to-one, in range, and nothing invented (F4.2)."""
    seen_existing: set[int] = set()
    seen_draft: set[int] = set()
    pairs: list[BulletPair] = []
    for row in pairing.pairs:
        if not 0 <= row.existing < existing_count:
            raise CitationViolation(f"existing index {row.existing} does not exist")
        if not 0 <= row.draft < draft_count:
            raise CitationViolation(f"draft index {row.draft} does not exist")
        if row.existing in seen_existing:
            raise CitationViolation(f"existing index {row.existing} was paired twice")
        if row.draft in seen_draft:
            raise CitationViolation(f"draft index {row.draft} was paired twice")
        seen_existing.add(row.existing)
        seen_draft.add(row.draft)
        pairs.append(BulletPair(existing=row.existing, draft=row.draft))
    return tuple(pairs)


def pair_bullets(
    session,
    *,
    existing: Sequence[str],
    draft: Sequence[str],
    lang_existing: str,
    lang_draft: str,
    model: str | None = None,
    options: CallOptions | None = None,
) -> PairingReport:
    """The pairs between two numbered lists of lines, and the calls that produced them.

    Both lists are numbered from zero here and the indexes are the only thing the
    model may cite back; the caller maps them onto rows. An empty side is answered
    without a call: nothing can pair with nothing, and asking would only cost a
    call to be told so.
    """
    if not existing or not draft:
        return PairingReport(pairs=())
    if len(set(existing)) != len(existing) or len(set(draft)) != len(draft):
        # Duplicated text makes an index answer ambiguous — two rows would be the
        # same line — and the caller has no business asking. Fail before paying.
        raise CitationViolation("pairing needs distinct lines to number")

    user = BULLET_PAIRING_V1.render(
        lang_existing=lang_existing,
        lang_draft=lang_draft,
        existing="\n".join(f"{index}\t{text}" for index, text in enumerate(existing)),
        draft="\n".join(f"{index}\t{text}" for index, text in enumerate(draft)),
    )
    attempts: list[Completion] = []
    for attempt in range(RETRIES + 1):
        completion = complete_json(
            session,
            purpose=PURPOSE,
            prompt_version=BULLET_PAIRING_V1.version,
            system=BULLET_PAIRING_V1.system,
            user=user
            if attempt == 0
            else f"{user}\n\nYour previous answer was unusable: cite only indexes "
            "from the two lists, and never the same index twice.",
            schema=BulletPairing,
            model=model,
            options=options,
        )
        attempts.append(completion)
        try:
            pairs = _validate(
                BulletPairing.model_validate(completion.data), len(existing), len(draft)
            )
        except CitationViolation:
            if attempt < RETRIES:
                continue
            raise
        return PairingReport(pairs=pairs, calls=tuple(attempts))

    raise CitationViolation("pairing failed after a retry")  # pragma: no cover - loop returns
