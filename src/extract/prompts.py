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

    def render_system(self, **values: object) -> str:
        """The invariant part, rendered.

        Providers price a cached prefix at a fraction of fresh input, so everything
        that does not change between postings lives in the system message and only
        the data varies. The vocabulary is data too (PRD design principle 4) and
        grows by alias promotion, so the prefix changes when the vocabulary does —
        which is correct, and busts the cache exactly once.
        """
        return self.system.format(**values) if values else self.system


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


JD_EXTRACTION = Prompt(
    version="jd_extract_v2",
    # Everything here is identical for every posting; the posting itself is the
    # whole user message. That ordering is what makes the vocabulary block a
    # cacheable prefix (v1 had the posting before the vocabulary, which destroyed
    # the common prefix on every call).
    system=(
        "You convert a job posting into structured data. You do not evaluate the "
        "posting and you never infer a requirement that is not written in it. For "
        "must_have and nice_to_have you may only use names from the vocabulary "
        "below; anything else the posting asks for goes into raw_keywords exactly "
        "as written. hard_requirements are conditions that could disqualify "
        "someone outright (a degree, work authorization, an on-site city).\n\n"
        "Posting language is one of: {languages}.\n\n"
        "Canonical skill vocabulary (use these exact strings for must_have and "
        "nice_to_have, and nothing else):\n{skills}\n\n"
        "Return the posting's language, title, seniority rung (intern, junior, "
        "mid, senior, lead, principal, or unknown), the years of experience it "
        "asks for if stated, the must-have and nice-to-have skills, the keywords "
        "it emphasises, any hard requirements, and its location policy if it "
        "states one."
    ),
    template="{text}",
)


EVIDENCE_GRADING = Prompt(
    version="evidence_grade_v2",
    # The rubric and the output contract are the same for every posting, so they
    # are the stable prefix; only the requirements and the bullets vary, and they
    # are the whole user message.
    system=(
        "You judge how strongly a person's own résumé bullets evidence each job "
        "requirement. Use exactly these levels: 0 absent — nothing supports it; "
        "1 mentioned — the skill appears in a list with no context; 2 applied — it "
        "was used in a described task; 3 demonstrated — it was used with scope or an "
        "outcome attached. For any level above 0 you must cite the id of the bullet "
        "that supports it. Never cite an id you were not given, and never assume "
        "experience the bullets do not show: an unsupported requirement is level 0, "
        "which is a normal and useful answer.\n\n"
        "Return one grade per requirement index: the level, the cited bullet id or "
        "null, and one short sentence if any requirement needs a caveat."
    ),
    template=(
        "Requirements to grade, by index:\n{requirements}\n\n"
        "The person's bullets (id, then text):\n{bullets}\n\n"
        "Write the caveat sentence in {lang}."
    ),
)


def summarize_rows(rows: list[str], *, empty: str = "(none)") -> str:
    return "\n".join(rows) if rows else empty
