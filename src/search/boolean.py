"""Boolean recall evaluation (PRD F5.2): deterministic, and no network call.

A recruiter's query is a tree of `and` / `or` / `not` over terms, and the question is
only whether this track's text would be returned by it. That is arithmetic over text
the user already wrote, so it is decided here — the same line the project draws
between the model's judgement (which terms matter, which the derivation call asks for)
and the deterministic core.

Terms match through the shared vocabulary's aliases, with spans consumed: a text
mentioning `machine learning` must not also satisfy a query for `learning`, or the
same phrase would answer two clauses (decision 6).
"""

from dataclasses import asdict, dataclass
from typing import Literal

from src.normalize.text import fold, term_pattern

# Where a term was found, and what a clause cites when it passes.
UnitKind = Literal["bullet", "skill", "headline", "summary", "role", "education", "certification"]

# Why a query failed. `missing` is the PRD's own case — no alias of the term appears;
# `present` is a `not` clause whose term the track does carry.
FailureKind = Literal["missing", "present"]


@dataclass(frozen=True)
class SearchUnit:
    """One piece of searchable text: a bullet, a skill chip, a title, a credential."""

    kind: str
    text: str
    bullet_id: str | None = None


@dataclass(frozen=True)
class ClauseResult:
    term: str
    matched: bool
    unit_kind: str | None = None
    bullet_id: str | None = None
    unit_text: str | None = None


@dataclass(frozen=True)
class QueryResult:
    label: str
    passed: bool
    clauses: tuple[ClauseResult, ...] = ()
    failing_term: str | None = None
    failing_kind: FailureKind | None = None


@dataclass(frozen=True)
class RecallReport:
    """What Scan B found. `checked` is False when there was nothing to check."""

    queries: tuple[QueryResult, ...] = ()
    units: int = 0
    checked: bool = False

    @property
    def passed(self) -> int:
        return sum(1 for query in self.queries if query.passed)

    @property
    def failed(self) -> int:
        return sum(1 for query in self.queries if not query.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "checked": self.checked,
            "units": self.units,
            "passed": self.passed,
            "failed": self.failed,
            "queries": [
                {
                    "label": query.label,
                    "passed": query.passed,
                    "failing_term": query.failing_term,
                    "failing_kind": query.failing_kind,
                    "clauses": [asdict(clause) for clause in query.clauses],
                }
                for query in self.queries
            ],
        }


def _matches(expr: object, hits: dict[str, SearchUnit]) -> bool:
    """Whether a node is satisfied by the terms that were found."""
    if isinstance(expr, str):
        term = expr.strip()
        return bool(term) and term in hits
    all_of = getattr(expr, "all_of", None)
    any_of = getattr(expr, "any_of", None)
    none_of = getattr(expr, "none_of", None)
    if all_of:
        return all(_matches(child, hits) for child in all_of)
    if any_of:
        return any(_matches(child, hits) for child in any_of)
    if none_of:
        return not any(_matches(child, hits) for child in none_of)
    return True  # a node with nothing in it constrains nothing


def terms_of(expr: object) -> list[str]:
    """Every term under a node, in the order it was written."""
    if isinstance(expr, str):
        return [expr.strip()] if expr.strip() else []
    found: list[str] = []
    for child in [
        *(getattr(expr, "all_of", None) or []),
        *(getattr(expr, "any_of", None) or []),
        *(getattr(expr, "none_of", None) or []),
    ]:
        found.extend(terms_of(child))
    return found


def _first_failure(expr: object, hits: dict[str, SearchUnit]) -> tuple[str, FailureKind] | None:
    """The first reason this node is false, named the way the panel shows it."""
    if isinstance(expr, str):
        term = expr.strip()
        if not term or term in hits:
            return None
        return term, "missing"
    all_of = getattr(expr, "all_of", None)
    any_of = getattr(expr, "any_of", None)
    none_of = getattr(expr, "none_of", None)
    if all_of:
        for child in all_of:
            failure = _first_failure(child, hits)
            if failure is not None:
                return failure
        return None
    if any_of:
        if _matches(expr, hits):
            return None
        return " / ".join(terms_of(expr)), "missing"
    if none_of:
        for child in none_of:
            if _matches(child, hits):
                return " / ".join(terms_of(child)), "present"
        return None
    return None


def alias_groups(aliases: dict[str, str]) -> dict[str, tuple[str, ...]]:
    """canonical → its aliases, longest first, so a phrase consumes its span."""
    groups: dict[str, list[str]] = {}
    for alias, canonical in aliases.items():
        groups.setdefault(canonical, []).append(alias)
    return {
        canonical: tuple(sorted(set(values), key=len, reverse=True))
        for canonical, values in groups.items()
    }


def _aliases_of(
    term: str, aliases: dict[str, str], groups: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    """The phrases that count as this term: its vocabulary aliases when it has any."""
    key = fold(term)
    canonical = aliases.get(key)
    return groups.get(canonical, (key,)) if canonical else (key,)


def match_terms(
    terms: list[str], units: list[SearchUnit], aliases: dict[str, str]
) -> dict[str, SearchUnit]:
    """Which unit satisfies each term, with alias spans consumed (decision 6)."""
    groups = alias_groups(aliases)
    haystacks = [fold(unit.text) for unit in units]
    consumed: list[list[tuple[int, int]]] = [[] for _ in units]
    hits: dict[str, SearchUnit] = {}

    candidates = [(alias, term) for term in terms for alias in _aliases_of(term, aliases, groups)]
    for alias, term in sorted(candidates, key=lambda pair: len(pair[0]), reverse=True):
        if term in hits or not alias:
            continue
        pattern = term_pattern(alias)
        for index, haystack in enumerate(haystacks):
            for match in pattern.finditer(haystack):
                start, end = match.span()
                taken = consumed[index]
                if any(start < taken_end and taken_start < end for taken_start, taken_end in taken):
                    continue
                taken.append((start, end))
                hits[term] = units[index]
                break
            if term in hits:
                break
    return hits


def evaluate(
    queries: list[object], units: list[SearchUnit], aliases: dict[str, str]
) -> RecallReport:
    """Run every query against the track's text.

    `queries` are `extract.boolean.BooleanQuery` values (or anything with `label` and
    `expr`), so this module never imports the model edge for a type only.
    """
    if not queries or not units:
        return RecallReport(queries=(), units=len(units), checked=False)

    positives = [term for query in queries for term in terms_of(getattr(query, "expr", None))]
    hits = match_terms(positives, units, aliases)

    results: list[QueryResult] = []
    for query in queries:
        expr = getattr(query, "expr", None)
        clauses = tuple(
            ClauseResult(
                term=term,
                matched=term in hits,
                unit_kind=hits[term].kind if term in hits else None,
                bullet_id=hits[term].bullet_id if term in hits else None,
                unit_text=hits[term].text if term in hits else None,
            )
            for term in terms_of(expr)
        )
        passed = _matches(expr, hits)
        failure = None if passed else _first_failure(expr, hits)
        results.append(
            QueryResult(
                label=str(getattr(query, "label", "") or ""),
                passed=passed,
                clauses=clauses,
                failing_term=failure[0] if failure else None,
                failing_kind=failure[1] if failure else None,
            )
        )
    return RecallReport(queries=tuple(results), units=len(units), checked=True)