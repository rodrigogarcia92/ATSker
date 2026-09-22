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


RESUME_EXTRACTION = Prompt(
    version="resume_extract_v1",
    # The rules and the vocabulary block are the system message, so repeated
    # uploads share a cacheable prefix exactly like the JD call (decision 18).
    system=(
        "You convert a résumé or CV into structured data. You extract only what "
        "the document states: never infer, complete or improve a date, an employer "
        "or a claim, and leave a field out when the document does not say it.\n\n"
        "The document's language is one of: {languages}. Return its ISO 639-1 code "
        "and keep every extracted string in the document's own language, as printed.\n\n"
        "Roles: one entry per position, with its bullet points exactly as written — "
        "do not merge two bullets into one, do not split one into two, and do not "
        "rephrase. A line without an employer or a title is not a role.\n\n"
        "Education and certifications: the document may print both under one heading, "
        "so return a single array of entries. For each entry give the name as printed "
        "(the award or the credential), the issuer, the field of study if stated, "
        "dates as YYYY-MM or YYYY, and a credential id or url only when one is "
        "printed. Propose a kind — education, certification or unsure — from what "
        "the document says; unsure is the right answer when it does not say.\n\n"
        "Skills: choose only names from the vocabulary below, and only the ones the "
        "document actually shows. Canonical name and kind:\n{skills}\n\n"
        "Return the headline (a one-line tagline, if the document has one), a "
        "summary paragraph if it has one, the roles with their bullets, the "
        "education and certification entries, and the skills."
    ),
    template="{text}",
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


GAP_INTERPRETATION = Prompt(
    version="gap_interpret_v1",
    # The contract is the same for every posting — what a gap note is, what the one
    # warning covers, what honesty about missing material means — so it is the
    # cacheable prefix and only the data varies (decision 18).
    system=(
        "You explain the gaps a deterministic analysis found between a person's "
        "résumé and a job posting. You discover nothing: the gaps you are given are "
        "the complete list, and you return exactly one note per gap, in the order "
        "given, with each requirement text copied unchanged. Reordering, dropping, "
        "rewriting or inventing a gap is a failure.\n\n"
        "For each gap set blocking to true when the gap alone would rule this "
        "candidate out of the posting — an unmet must-have the employer insists on "
        "— and false when it weakens the application without ending it. Write one "
        "line of interpretation per gap: what it costs this application, and what "
        "material could answer it.\n\n"
        "Return exactly one warning, covering only the standing risks that actually "
        "bite on this posting plus anything posting-specific, with a suggested "
        "handling. If nothing bites, leave the warning empty; do not invent one, and "
        "never turn it into a list of everything that could conceivably go wrong.\n\n"
        "Return also one sentence naming what was not found in the person's data — "
        "missing material, stated plainly rather than filler. When the stories block "
        "says none were available, say that no stories were available; never imply "
        "that none were relevant."
    ),
    template=(
        "The gaps, in order (index, level, weight, requirement, and the bullet that "
        "came close when there is one):\n{gaps}\n\n"
        "The posting as extracted:\n{posting}\n\n"
        "The person's standing risks — check each against this posting; the warning "
        "mentions only the ones that bite here:\n{risks}\n\n"
        "Their career stories — material an answer could draw on:\n{stories}\n\n"
        "Write every sentence in {lang}."
    ),
)


BOOLEAN_RECALL = Prompt(
    version="boolean_recall_v1",
    # Instructions and vocabulary are the stable prefix; the posting is the whole user
    # message, exactly like the other two extraction calls (decision 18).
    system=(
        "You write the boolean searches a recruiter would actually run to find a "
        "candidate for a posting — in an ATS, on LinkedIn Recruiter, or on a job "
        "board. Return three to five queries, ordered from broadest to narrowest.\n\n"
        "A query is a tree of and / or / not over terms, written as JSON. A term is "
        "a phrase exactly as a recruiter would type it. A node is a single object "
        "with exactly one key — \"and\", \"or\" or \"not\" — whose value is an array "
        "of items, each of which is a term or another node. Use \"not\" only to "
        "exclude something the posting rules out.\n\n"
        "The broadest query holds what nobody would drop — the posting's own title "
        "and one or two core skills; the narrowest holds everything it insists on.\n\n"
        "Terms come from the posting. Where the posting names something in this "
        "vocabulary, use the canonical name exactly as written here, because that is "
        "what a résumé is actually written in:\n{vocabulary}\n\n"
        "Never invent a requirement the posting does not state, and keep each query "
        "to what a person could type in one line."
    ),
    template="{posting}",
)
