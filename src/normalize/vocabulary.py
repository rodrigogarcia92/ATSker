"""Vocabulary matching: prose and user-typed terms → canonical skills.

Pure functions over a folded alias map, so the rules are testable without a
database. A longer alias consumes its span, which is what stops a text mentioning
`machine learning` from also reporting the separate skill `learning`: the same
phrase must not be counted twice when sub-scores weight evidence.
"""

from collections.abc import Iterable, Mapping

from src.normalize.text import fold, term_pattern


def match_text(text: str, aliases: Mapping[str, str], *, limit: int | None = None) -> list[str]:
    """Canonical skills whose alias appears as a whole, unconsumed term in `text`."""
    haystack = fold(text)
    consumed: list[tuple[int, int]] = []
    found: list[str] = []

    for alias in sorted(aliases, key=len, reverse=True):
        canonical = aliases[alias]
        if canonical in found:
            continue
        for match in term_pattern(alias).finditer(haystack):
            start, end = match.span()
            if any(start < taken_end and taken_start < end for taken_start, taken_end in consumed):
                continue
            consumed.append((start, end))
            found.append(canonical)
            break
        if limit is not None and len(found) >= limit:
            break
    return found


def resolve_terms(terms: Iterable[str], aliases: Mapping[str, str]) -> tuple[list[str], list[str]]:
    """User-typed terms → (canonical skills, terms the vocabulary does not know).

    Unknown terms are returned rather than dropped: F3 logs them as candidates for
    alias promotion, which is the only way the vocabulary grows.
    """
    canonical: list[str] = []
    unmatched: list[str] = []
    for raw in terms:
        term = fold(raw)
        if not term:
            continue
        known = aliases.get(term)
        if known is not None:
            if known not in canonical:
                canonical.append(known)
        elif term not in unmatched:
            unmatched.append(term)
    return canonical, unmatched
