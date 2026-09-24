"""The text a boolean query — and the keyword scorer — runs against (PRD F5.2).

What the document contains is decided in one place, `src.documents.track_document`:
this module only maps those units to `SearchUnit`s and keeps the order the search
panel has always shown them in, so the two scans and the number cannot disagree
about the person's career (F5.5.1).

Two scope decisions travel from the old implementation:

- the evidence is the same evidence the score reads — the track's selection, or
  every active bullet when there is no track;
- `profiles.skills` is still not read (decision 32): it is annotation from a
  résumé review and cannot lift a number. The reversal in F5.4.1 is only for the
  track's own `tracks.skills` — the selection is the skills section a reader sees,
  and a real ATS keyword search runs over exactly that.
"""

from collections.abc import Sequence

from src.documents import DocumentUnit
from src.search.boolean import SearchUnit

# The panel's order, unchanged since F5.2: bullets, skills, headline, summary,
# roles, education, certifications.
_BUCKETS: tuple[tuple[str, ...], ...] = (
    ("bullet",),
    ("skill", "skills_list"),
    ("headline",),
    ("summary",),
    ("role",),
    ("education",),
    ("certification",),
)


def searchable_units(document: Sequence[DocumentUnit]) -> list[SearchUnit]:
    """Every piece of the document's text, one unit at a time.

    A no-track document yields byte-identical output to the pre-F4.1
    `searchable_units`: same units, same order. The skills section — the track's
    selection, or the bullets' chips without a track — is searchable as `skill`
    units either way.
    """
    units: list[SearchUnit] = []
    for kinds in _BUCKETS:
        for unit in document:
            if unit.kind not in kinds or not unit.text:
                continue
            kind = "skill" if unit.kind in ("skill", "skills_list") else unit.kind
            cited = unit.source_id if unit.kind == "bullet" else None
            units.append(SearchUnit(kind, unit.text, cited))
    return units
