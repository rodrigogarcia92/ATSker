"""Title alignment (weight 0.20).

Alias-expanded token overlap, then a penalty for sitting on the wrong rung of the
seniority ladder. Inputs are the JD, the profile headline, and the titles of the
roles the user has actually held — never a guess at what would sound better.
"""

from collections.abc import Mapping, Sequence

from src.jd import StructuredJD, seniority_rung
from src.normalize.text import fold
from src.score.aggregate import SubScore

PENALTY_ONE_RUNG = 0.2
PENALTY_MANY_RUNGS = 0.5

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
    role_titles: Sequence[str],
    aliases: Mapping[str, str] | None = None,
) -> SubScore:
    wanted = title_tokens(jd.title, aliases)
    available: set[str] = set()
    for text in (headline, *role_titles):
        available |= title_tokens(text or "", aliases)

    matched = sorted(wanted & available)
    missing = sorted(wanted - available)
    overlap = len(matched) / len(wanted) if wanted else 0.0

    candidate_rungs = [
        rung
        for rung in (seniority_of(text) for text in (headline, *role_titles))
        if rung is not None
    ]
    user_rung = (
        max(candidate_rungs, key=lambda rung: seniority_rung(rung) or 0)
        if candidate_rungs
        else None
    )
    jd_rung = jd.seniority if jd.seniority != "unknown" else seniority_of(jd.title)

    penalty = 0.0
    distance = None
    if user_rung is not None and jd_rung is not None:
        jd_index, user_index = seniority_rung(jd_rung), seniority_rung(user_rung)
        if jd_index is not None and user_index is not None:
            distance = abs(jd_index - user_index)
            if distance == 1:
                penalty = PENALTY_ONE_RUNG
            elif distance >= 2:
                penalty = PENALTY_MANY_RUNGS

    value = max(0.0, overlap - penalty)
    return SubScore(
        name="title",
        value=round(value, 4),
        matched=matched,
        missing=missing,
        detail={
            "overlap": round(overlap, 4),
            "penalty": penalty,
            "rung_distance": distance,
            "user_rung": user_rung,
            "jd_rung": jd_rung,
        },
    )
