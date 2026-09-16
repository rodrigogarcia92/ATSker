"""Versioned prompts (PRD 7).

A change to a prompt means a new version string, which busts the cache on purpose:
scores and suggestions produced under different prompts are never compared.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    version: str
    system: str
    template: str

    def render(self, **values: object) -> str:
        return self.template.format(**values)


STORY_SUGGESTION = Prompt(
    version="story_suggest_v1",
    system=(
        "You help a job seeker tag their own career stories. You may only choose "
        "from the identifiers and skill names given to you; inventing one is a "
        "failure. If nothing fits, return an empty list for that field."
    ),
    template=(
        "Story titled {title!r} (written in {lang}).\n\n"
        "Story text:\n{body}\n\n"
        "Roles the person has held (choose at most one id for the story's main role):\n"
        "{roles}\n\n"
        "Bullets already in their profile that this story relates to "
        "(choose only ids from this list):\n{bullets}\n\n"
        "Canonical skills from their vocabulary that the story actually demonstrates "
        "(choose only names from this list):\n{skills}\n\n"
        "Return the best role id or null, up to five bullet ids, up to six skills, "
        "and one short sentence in {lang} explaining the choice."
    ),
)


def summarize_rows(rows: list[str], *, empty: str = "(none)") -> str:
    return "\n".join(rows) if rows else empty
