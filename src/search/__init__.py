"""Scan B — boolean search recall (PRD F5.2).

Two halves, split the way the whole project is: `boolean` decides, from the queries
and the track's text, whether a recruiter's search would return this track, and
`sources` assembles the text that search runs against. Neither makes a network call —
that is the rule `tests/unit/test_boundaries.py` enforces for this package.

Recall is a gate, not a term in the score (F5.2): a track that fails the broad query
has a problem no score improvement fixes, and blending it into the number would hide
that behind a percentage.
"""

from src.search.boolean import (
    ClauseResult,
    QueryResult,
    RecallReport,
    SearchUnit,
    evaluate,
)
from src.search.sources import searchable_units

__all__ = [
    "ClauseResult",
    "QueryResult",
    "RecallReport",
    "SearchUnit",
    "evaluate",
    "searchable_units",
]