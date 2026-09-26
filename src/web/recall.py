"""A stored boolean-recall result, translated for a panel (PRD F5.2).

The panel's job is to say one thing clearly: a recruiter running this query would not
find this track, and here is the clause that excludes it. The numbers beside it — how
many queries pass — are context, not a score.
"""

from collections.abc import Mapping
from typing import Any

from src.i18n import t


def query_rows(payload: Mapping[str, Any], lang: str) -> list[dict[str, Any]]:
    """One row per derived query, with its failing clause already in words."""
    rows: list[dict[str, Any]] = []
    for query in payload.get("queries", []):
        failing_term = query.get("failing_term")
        failing_kind = query.get("failing_kind")
        rows.append(
            {
                "label": str(query.get("label") or ""),
                "passed": bool(query.get("passed")),
                # A.9.2: the line the user pastes into the ATS. Empty for a report
                # stored before the field existed, and the panel shows nothing then.
                "query_text": str(query.get("query_text") or ""),
                "failing": (
                    t(f"recall.fail.{failing_kind}", lang, term=failing_term)
                    if failing_term and failing_kind
                    else None
                ),
                "clauses": [
                    {
                        "term": str(clause.get("term") or ""),
                        "matched": bool(clause.get("matched")),
                        "unit": t(f"recall.unit.{clause.get('unit_kind')}", lang)
                        if clause.get("unit_kind")
                        else "",
                        "text": str(clause.get("unit_text") or ""),
                    }
                    for clause in query.get("clauses", [])
                ],
            }
        )
    return rows