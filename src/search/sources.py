"""The text a boolean query runs against (PRD F5.2).

F5.2 names it: a track's bullets, skills, headline, summary, role titles, education
and certifications. Two scope decisions are worth stating, because both are decisions
this project already made elsewhere:

- the evidence is the same evidence the score reads — the track's selection, or every
  active bullet when there is no track — so the two scans and the number cannot
  disagree about what the person's career contains;
- `profiles.skills` is left out (decision 32): it is annotation from a résumé review
  and cannot lift a number, so it cannot satisfy a recruiter's query either.
"""

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from src.bullets import bullet_text
from src.certifications import list_certifications
from src.education import list_educations
from src.models import Bullet
from src.search.boolean import SearchUnit


def searchable_units(
    profile_id: uuid.UUID,
    session: Session,
    *,
    bullets: Sequence[Bullet],
    headline: str | None = None,
    summary: str | None = None,
    role_titles: Sequence[str] = (),
) -> list[SearchUnit]:
    """Every piece of a track's text, one unit at a time, in a stable order."""
    units = [
        SearchUnit("bullet", bullet_text(bullet), str(bullet.id))
        for bullet in bullets
        if bullet_text(bullet)
    ]
    units += [
        SearchUnit("skill", skill)
        for skill in sorted({skill for bullet in bullets for skill in bullet.skills})
    ]
    if headline:
        units.append(SearchUnit("headline", headline))
    if summary:
        units.append(SearchUnit("summary", summary))
    units += [SearchUnit("role", title) for title in role_titles if title]
    units += [
        SearchUnit(
            "education",
            " ".join(part for part in (entry.institution, entry.degree, entry.field) if part),
        )
        for entry in list_educations(profile_id, session)
    ]
    units += [
        SearchUnit("certification", " ".join(part for part in (entry.name, entry.issuer) if part))
        for entry in list_certifications(profile_id, session)
    ]
    return units