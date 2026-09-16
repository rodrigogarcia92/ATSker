"""Metric extraction: the numbers a résumé bullet is worth.

Deterministic and reused by F7's literal-preservation validator (M8), which must
find in the source bullet every number the rewritten bullet claims. One definition
for both means the validator cannot disagree with what was stored.
"""

import re

_NUMBER = r"[+\-]?\$?\d[\d.,]*"
_UNITS = (
    r"%|x|k|m|mm|bn|usd|eur|pen|us\$|s/|anos?|años?|years?|meses?|months?|"
    r"semanas?|weeks?|dias?|días?|days?|horas?|hours?|minutos?|minutes?"
)
_METRIC = re.compile(rf"(?<![a-z0-9]){_NUMBER}\s?(?:{_UNITS})?(?![a-z0-9])", re.IGNORECASE)


def extract_metrics(text: str) -> list[str]:
    """Numeric tokens in order, deduplicated, whitespace-normalised."""
    found: list[str] = []
    for match in _METRIC.finditer(text):
        token = " ".join(match.group(0).split())
        if token not in found:
            found.append(token)
    return found
