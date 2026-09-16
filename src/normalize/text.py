"""Folding, so `Análisis` and `analisis` collide (PRD 8)."""

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def fold(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _WHITESPACE.sub(" ", without_marks).strip().lower()


def term_pattern(folded_term: str) -> re.Pattern[str]:
    """Whole-term search that survives `c++`, `node.js` and multi-word entries.

    `\\b` is useless here: `+` and `.` are not word characters, so a plain boundary
    would match `c` inside `c++`. Boundaries are "not alphanumeric and not an
    operator character" instead; a dotted pair like `node` / `node.js` is left to
    span consumption in `normalize.vocabulary`, which matches the longer term first.
    """
    return re.compile(rf"(?<![a-z0-9+#]){re.escape(folded_term)}(?![a-z0-9+#])")
