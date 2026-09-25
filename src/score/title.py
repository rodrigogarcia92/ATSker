"""Title alignment (weight 0.20).

Alias-expanded token overlap with the function words removed, and nothing else:
seniority never enters the number (PRD F5.5.2). The rung a title sits on is still
read — the most recent role's title, else the track's headline — but only to raise
an alert in either direction, beside the score and never inside it. Inputs are the
JD, the track headline, and the roles the user has actually held with their dates —
never a guess at what would sound better.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path

from src.jd import StructuredJD, seniority_rung
from src.normalize.text import fold
from src.score.aggregate import SubScore

# PRD F5.5.2: both languages' function words are removed from both sides, so a
# Spanish posting and an English headline are compared on their content words.
FUNCTION_WORDS: frozenset[str] = frozenset(
    word
    for words in json.loads(
        (Path(__file__).resolve().parents[1] / "normalize" / "function_words.json").read_text(
            encoding="utf-8"
        )
    ).values()
    for word in words
)

_RUNG_WORDS = {
    "intern": "intern",
    "becario": "intern",
    "practicante": "intern",
    "trainee": "intern",
    "junior": "junior",
    "jr": "junior",
    "mid": "mid",
    "semi": "mid",
    "senior": "senior",
    "sr": "senior",
    "lead": "lead",
    "lider": "lead",
    "líder": "lead",
    "staff": "lead",
    "principal": "principal",
    "head": "principal",
    "director": "principal",
    "manager": "lead",
    "jefe": "lead",
}


def _expand(token: str, aliases: Mapping[str, str]) -> set[str]:
    canonical = aliases.get(token)
    if canonical is None:
        return {token}
    return set(canonical.split())


def title_tokens(text: str, aliases: Mapping[str, str] | None = None) -> set[str]:
    """Folded tokens, with each token replaced by its canonical vocabulary tokens."""
    folded = fold(text)
    raw = [token for token in fold(folded.replace("|", " ").replace("/", " ")).split() if token]
    tokens: set[str] = set()
    for token in raw:
        cleaned = token.strip(".,;:()[]{}")
        if cleaned:
            tokens |= _expand(cleaned, aliases or {})
    return tokens


def seniority_of(title: str | None) -> str | None:
    """The rung a title sits on, if its words name one."""
    if not title:
        return None
    rungs = [_RUNG_WORDS[token] for token in fold(title).split() if token in _RUNG_WORDS]
    if not rungs:
        return None
    return max(rungs, key=lambda rung: seniority_rung(rung) or 0)


def title_alignment(
    jd: StructuredJD,
    *,
    headline: str | None,
    roles: Sequence[tuple[str, date | None, date | None]],
    aliases: Mapping[str, str] | None = None,
) -> SubScore:
    """Word overlap only (`w4`, PRD F5.5.2).

    `roles` is (title, start_date, end_date) in any order. The most recent one —
    an open role first, the latest start among those, else the latest end date —
    is the only title that may name the user's rung; earlier titles never do. No
    rung there falls back to the track headline, and neither means the rung is
    unknown: no alert, never an invented one.
    """
    wanted = title_tokens(jd.title, aliases) - FUNCTION_WORDS
    available: set[str] = set()
    for text in (headline, *(title for title, _, _ in roles)):
        available |= title_tokens(text or "", aliases)
    available -= FUNCTION_WORDS

    matched = sorted(wanted & available)
    missing = sorted(wanted - available)
    overlap = len(matched) / len(wanted) if wanted else 0.0

    open_roles = [role for role in roles if role[2] is None]
    if open_roles:
        most_recent = max(open_roles, key=lambda role: role[1] or date.min)
    elif roles:
        most_recent = max(roles, key=lambda role: role[2] or date.min)
    else:
        most_recent = None
    user_rung = seniority_of(most_recent[0]) if most_recent else None
    if user_rung is None:
        user_rung = seniority_of(headline)
    jd_rung = jd.seniority if jd.seniority != "unknown" else seniority_of(jd.title)

    distance = None
    seniority_above = False
    seniority_below = False
    if user_rung is not None and jd_rung is not None:
        jd_index, user_index = seniority_rung(jd_rung), seniority_rung(user_rung)
        if jd_index is not None and user_index is not None:
            distance = abs(jd_index - user_index)
            seniority_above = user_index > jd_index
            seniority_below = user_index < jd_index

    detail: dict[str, object] = {
        "overlap": round(overlap, 4),
        "user_rung": user_rung,
        "jd_rung": jd_rung,
        "rung_distance": distance,
        "seniority_above": seniority_above,
        "seniority_below": seniority_below,
    }
    if not wanted:
        # An overlap of zero through an emptied wanted set is not a mismatch; the
        # report must be able to say which it was.
        detail["reason"] = "only_function_words"

    return SubScore(
        name="title",
        value=round(overlap, 4),
        matched=matched,
        missing=missing,
        detail=detail,
    )
