"""Redaction before any text leaves for a model provider (PRD 10).

Honest scope: emails and phone numbers are matched by pattern, and the user's own
name is matched by the words we already know (`display_name`). A name that appears
only in a document and nowhere in the profile is not detected — this pass reduces
exposure, it does not guarantee anonymity, and the PRD's informed-consent statement
to both users is what covers the remainder.
"""

import re

from src.normalize.text import fold, term_pattern

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d[\d\s.-]{6,}\d(?!\w)")
_URL = re.compile(r"https?://\S+")

EMAIL_TOKEN = "[email]"
PHONE_TOKEN = "[phone]"
URL_TOKEN = "[url]"
NAME_TOKEN = "[name]"


def redact(text: str, *, known_names: list[str] | None = None) -> str:
    """Pattern-redact contact details and the names we know about."""
    redacted = _URL.sub(URL_TOKEN, text)
    redacted = _EMAIL.sub(EMAIL_TOKEN, redacted)
    redacted = _PHONE.sub(PHONE_TOKEN, redacted)

    folded = fold(redacted)
    for name in known_names or []:
        for word in [part for part in fold(name).split() if len(part) > 2]:
            for match in reversed(list(term_pattern(word).finditer(folded))):
                redacted = redacted[: match.start()] + NAME_TOKEN + redacted[match.end() :]
                folded = fold(redacted)
    return redacted
