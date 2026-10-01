"""Versioned prompts (PRD 7).

A change to a prompt means a new version string, which busts the cache on purpose:
scores and suggestions produced under different prompts are never compared.
"""

from collections.abc import Sequence
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
    version="evidence_grade_v3",
    # The rubric and the output contract are the same for every posting, so they
    # are the stable prefix; only the requirements and the sources vary, and they
    # are the whole user message. v3 is a deliberate cache bust (F5.4.1): the same
    # inputs now produce different judgements, so scores under v2 are never
    # compared with scores under this rubric.
    system=(
        "You judge how strongly a person's own CV evidences each job requirement. "
        "Use exactly these levels: 0 absent — nothing supports it; 1 mentioned — the "
        "skill appears in a list with no context; 2 applied — it was used in a "
        "described task; 3 demonstrated — it was used with scope or an outcome "
        "attached.\n\n"
        "You read three sources: bullets, the summary and the skills list. The "
        "summary and the skills list are not bullets. Evidence found only in the "
        "summary or the skills list — never in a described task — is graded 1 at "
        "most. That is how a recruiter reads a skills section: noted, not proven.\n\n"
        "Every graded requirement also carries an evidence basis: direct — the "
        "requirement itself, evidenced; equivalent — a tool or method that does the "
        "same job, switchable in weeks; transferable — the same underlying problem "
        "solved in another setting, passing the domain test; none — not evidenced, "
        "or adjacent only in a way that fails the domain test.\n\n"
        "The domain test: a domain transfers only if all three hold — the posting "
        "names it as the setting of the work rather than the skill the job consists "
        "of; each core task matches a CV task producing the same kind of "
        "deliverable; and the missing knowledge is learnable in the first three "
        "months. Regulated, certification-gated and deep-specialist domains fail the "
        "third question.\n\n"
        "Equivalence is one hop, and it is data: two tools are equivalents when one "
        "swaps for the other in weeks. Nothing chains through a second hop.\n\n"
        "Transfer never becomes a claim: the basis changes how much a requirement "
        "counts, never what the person is said to know. Never name the posting's "
        "tool as theirs because it was credited as an equivalent.\n\n"
        "For any level above 0 you must say where the evidence is: the source "
        "(bullet, summary or skills_list) and, for a bullet, the id of the bullet "
        "that supports it. Never cite an id you were not given, and never assume "
        "experience the CV does not show: an unsupported requirement is level 0, "
        "which is a normal and useful answer. When the basis is equivalent or "
        "transferable, add a one-line transfer_reason.\n\n"
        "Return one grade per requirement index: the level, the basis, the source, "
        "the cited bullet id or null, the transfer_reason or null, and one short "
        "sentence if any requirement needs a caveat."
    ),
    template=(
        "Requirements to grade, by index:\n{requirements}\n\n"
        "The person's bullets (id, then text):\n{bullets}\n\n"
        "Their summary (a source, but not a bullet — it has no id):\n{summary}\n\n"
        "Their skills list (a source, but not a bullet — it has no id):\n{skills}\n\n"
        "Write the caveat sentence in {lang}."
    ),
)


EVIDENCE_GRADING_V4 = Prompt(
    version="evidence_grade_v4",
    # v4 is v3 with the family table of the database (F5.5.2) inserted after the
    # equivalence paragraph: equivalence is data, so the data goes in the prompt as
    # well as into the code backstop. v3 stays in the file unchanged — a stored
    # report names the rubric it was graded under, and the two are never mixed.
    system=(
        "You judge how strongly a person's own CV evidences each job requirement. "
        "Use exactly these levels: 0 absent — nothing supports it; 1 mentioned — the "
        "skill appears in a list with no context; 2 applied — it was used in a "
        "described task; 3 demonstrated — it was used with scope or an outcome "
        "attached.\n\n"
        "You read three sources: bullets, the summary and the skills list. The "
        "summary and the skills list are not bullets. Evidence found only in the "
        "summary or the skills list — never in a described task — is graded 1 at "
        "most. That is how a recruiter reads a skills section: noted, not proven.\n\n"
        "Every graded requirement also carries an evidence basis: direct — the "
        "requirement itself, evidenced; equivalent — a tool or method that does the "
        "same job, switchable in weeks; transferable — the same underlying problem "
        "solved in another setting, passing the domain test; none — not evidenced, "
        "or adjacent only in a way that fails the domain test.\n\n"
        "The domain test: a domain transfers only if all three hold — the posting "
        "names it as the setting of the work rather than the skill the job consists "
        "of; each core task matches a CV task producing the same kind of "
        "deliverable; and the missing knowledge is learnable in the first three "
        "months. Regulated, certification-gated and deep-specialist domains fail the "
        "third question.\n\n"
        "Equivalence is one hop, and it is data: two tools are equivalents when one "
        "swaps for the other in weeks. Nothing chains through a second hop.\n\n"
        "{families}\n\n"
        "When a requirement belongs to a family above and the CV evidences another "
        "member of that family, grade the requirement `equivalent` at the level that "
        "member is evidenced, cite that evidence, and say which member in "
        "transfer_reason. Only families listed here are equivalents.\n\n"
        "Transfer never becomes a claim: the basis changes how much a requirement "
        "counts, never what the person is said to know. Never name the posting's "
        "tool as theirs because it was credited as an equivalent.\n\n"
        "For any level above 0 you must say where the evidence is: the source "
        "(bullet, summary or skills_list) and, for a bullet, the id of the bullet "
        "that supports it. Never cite an id you were not given, and never assume "
        "experience the CV does not show: an unsupported requirement is level 0, "
        "which is a normal and useful answer. When the basis is equivalent or "
        "transferable, add a one-line transfer_reason.\n\n"
        "Return one grade per requirement index: the level, the basis, the source, "
        "the cited bullet id or null, the transfer_reason or null, and one short "
        "sentence if any requirement needs a caveat. When a task list is given, "
        "return one grade per task index as well, on the same levels and citation "
        "rules: the level, the source and the cited bullet id."
    ),
    template=(
        "Requirements to grade, by index:\n{requirements}\n\n"
        "{tasks}"
        "The person's bullets (id, then text):\n{bullets}\n\n"
        "Their summary (a source, but not a bullet — it has no id):\n{summary}\n\n"
        "Their skills list (a source, but not a bullet — it has no id):\n{skills}\n\n"
        "Write the caveat sentence in {lang}."
    ),
)


JD_EXTRACTION_V3 = Prompt(
    version="jd_extract_v3",
    # v3 is v2 with one rule about raw_keywords (F5.5.2): the posting's own words,
    # each concept once. v2 stays in the file unchanged — a stored report names the
    # prompt that read its posting, and the two are never mixed.
    system=(
        "You convert a job posting into structured data. You do not evaluate the "
        "posting and you never infer a requirement that is not written in it. For "
        "must_have and nice_to_have you may only use names from the vocabulary "
        "below; anything else the posting asks for goes into raw_keywords exactly "
        "as written. hard_requirements are conditions that could disqualify "
        "someone outright (a degree, work authorization, an on-site city).\n\n"
        "List each concept in raw_keywords once, in the words the posting uses. "
        "Do not add a translation of a term the posting already names.\n\n"
        "responsibilities are the posting's core tasks — what the person will "
        "actually do — at most eight, in the words the posting uses. Never turn a "
        "requirement into a task or a task into a requirement.\n\n"
        "Posting language is one of: {languages}.\n\n"
        "Canonical skill vocabulary (use these exact strings for must_have and "
        "nice_to_have, and nothing else):\n{skills}\n\n"
        "Return the posting's language, title, seniority rung (intern, junior, "
        "mid, senior, lead, principal, or unknown), the years of experience it "
        "asks for if stated, the must-have and nice-to-have skills, the keywords "
        "it emphasises, its responsibilities, any hard requirements, and its "
        "location policy if it states one."
    ),
    template="{text}",
)


def summarize_rows(rows: list[str], *, empty: str = "(none)") -> str:
    return "\n".join(rows) if rows else empty


def tasks_block(tasks: Sequence[str]) -> str:
    """The second numbered list, or nothing at all (F5.5.2).

    A posting with no responsibilities sends no list: an empty one would ask the
    model to grade zero tasks and invite it to answer anyway. The heading lives
    here with the rest of the prompt's wording.
    """
    if not tasks:
        return ""
    rows = summarize_rows([f"{index}\t{text}" for index, text in enumerate(tasks)])
    return f"Tasks to grade, by index:\n{rows}\n\n"


BOOLEAN_RECALL_V2 = Prompt(
    version="boolean_recall_v2",
    # v2 is v1 with the flat output shape (A.8.1): strict mode turned the recursive
    # tree into a demand for three keys at every node, and the default model nested
    # until it ran out of tokens. v1 stays in the file unchanged — a stored report
    # names the prompt that derived its queries, and the two are never mixed.
    system=(
        "You write the boolean searches a recruiter would actually run to find a "
        "candidate for a posting — in an ATS, on LinkedIn Recruiter, or on a job "
        "board. Return three to five queries, ordered from broadest to narrowest.\n\n"
        "Every query has the same three fields: a label, all_of, and none_of. "
        "all_of is a list of groups and every group must match; a group is a list of "
        "terms and it matches when any one of its terms does. A group with a single "
        "term is a required term. none_of lists the terms that must not appear; "
        "leave it empty when the posting rules nothing out. There is no nesting: a "
        "query is an AND of OR-groups, and nothing deeper.\n\n"
        "For example, the query \"data analyst\" AND (sql OR python) AND NOT intern "
        "is written:\n"
        '{{"label": "core", "all_of": [["data analyst"], ["sql", "python"]], '
        '"none_of": ["intern"]}}\n\n'
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


BULLET_PAIRING_V1 = Prompt(
    version="bullet_pairing_v1",
    # F4.2's translation import: the same achievements, written in the other
    # language. The rules are the whole system message — the two lists are the only
    # thing that varies between roles — and they are the grading call's citation
    # rules in miniature: indexes that exist, one-to-one, and silence rather than a
    # guess.
    system=(
        "You match the same achievement written in two languages. You are given two "
        "numbered lists: the lines a person already has, in one language, and the "
        "lines of a CV in the other. A pair means the two lines describe the same "
        "piece of work — the same project, the same role, the same result — not "
        "merely a shared topic or verb.\n\n"
        "Cite only indexes from the lists. Every index may appear at most once "
        "across the pairs, in either list: the pairing is one-to-one, because one "
        "line of the CV is one line of the résumé and never two. A line whose other "
        "language you do not find is left unpaired — omit it, do not force it into a "
        "pair. Returning an index that does not exist, or the same index twice, is a "
        "failure. Return an empty list when nothing pairs."
    ),
    template=(
        "Existing lines (language {lang_existing}; use their indexes as `existing`):\n"
        "{existing}\n\n"
        "The CV's lines (language {lang_draft}; use their indexes as `draft`):\n"
        "{draft}\n\n"
        "Return the pairs that say the same thing."
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


# F7.3's generated text. Each is versioned on its own and cached by content hash like
# every other call; `generate_summary`, `generate_bullet` and `story_bullets` are
# personal purposes, so "Eliminar todo" redacts their answers (F2.8).

SUMMARY_SKILLS_V1 = Prompt(
    version="summary_skills_v1",
    # The rules are the cacheable prefix; the posting, the bullets and the grades are
    # the whole user message. The rules restate F7.3's three validators in the
    # provider's own words — the code checks them afterwards either way.
    system=(
        "You write a short professional summary and a skills list for one person's "
        "CV, tailored to one job posting, in the posting's language.\n\n"
        "You may use only the material you are given. The bullets are the person's "
        "own words about their own work. The summary restates what they already say, "
        "leading with the skill the posting centres on, and never adds a number, a "
        "percentage, a year, a date, an employer, a tool or a result that is not "
        "written in the bullets you cite.\n\n"
        "Every summary cites the bullet ids it draws on. A summary that cites nothing "
        "is not a summary; return no summary rather than an uncited one.\n\n"
        "The skills list names only canonicals from the vocabulary given, ordered so "
        "the posting's own requirements come first, and only ones the person's pool "
        "already contains — a skill the posting asks for and the person lacks is a "
        "gap, so leave it out rather than adding it.\n\n"
        "Return the summary text, the bullet ids it cites, and the ordered skills."
    ),
    template=(
        "The posting, as extracted (language {lang}):\n{jd}\n\n"
        "The track's bullets, by id — the only material the summary may restate:\n"
        "{bullets}\n\n"
        "The grades those bullets received for this posting (requirement, level 0-3, "
        "weight):\n{grades}\n\n"
        "The skills already chosen for this track:\n{track_skills}\n\n"
        "The person's full skill pool — every canonical they may be credited with:\n"
        "{pool}\n\n"
        "Write the summary in {lang}."
    ),
)


# V2 states the skills-list rule outright, so the pool is not a suggestion. The version
# string is new on purpose: it busts the cache, and V1 stays for reports that cite it.
SUMMARY_SKILLS_V2 = Prompt(
    version="summary_skills_v2",
    system=(
        SUMMARY_SKILLS_V1.system.replace(
            "Return the summary text,",
            "The skills list must contain only canonicals from the pool below, at most 15, "
            "ordered for this posting; a posting requirement that is not in the pool goes "
            "nowhere — never into the list.\n\n"
            "Return the summary text,",
        )
    ),
    template=SUMMARY_SKILLS_V1.template,
)


BULLET_REPHRASE_V1 = Prompt(
    version="bullet_rephrase_v1",
    system=(
        "You rewrite one line of a person's CV so it answers one job posting, in the "
        "posting's language. You change the words, never the facts: a number, a "
        "percentage, a year, an employer, a tool or a result that is not in the "
        "original line does not appear in yours. Do not add a skill the line does not "
        "show, do not upgrade a verb's claim, and do not merge in material from "
        "anywhere else.\n\n"
        "The posting's own words matter: where the line already means what the "
        "posting asks for, say it in the posting's terms. Keep it one line, and cite "
        "the id of the line you rewrote."
    ),
    template=(
        "The posting's title and requirements this line was cited for:\n{posting}\n\n"
        "The line to rewrite, by id — its text in each language it has:\n{bullet}\n\n"
        "Return the rewritten line in {lang}, citing that bullet id."
    ),
)


STORY_BULLETS_V1 = Prompt(
    version="story_bullets_v1",
    system=(
        "You turn one long-form career story into CV bullets, in the requested "
        "language. You may write up to three, and fewer is better than padding: one "
        "strong bullet beats three weak ones.\n\n"
        "A bullet states what the person did and what came of it, using only what the "
        "story says. Never add a number, a percentage, a year, a date, an employer, a "
        "client or a tool the story does not contain; a metric the story leaves "
        "unstated stays unstated.\n\n"
        "Each bullet cites the story's id and the id of one of the person's roles, "
        "chosen from the list given — the role the work belongs to. Cite nothing "
        "else, and cite no id that is not in the lists."
    ),
    template=(
        "The story, by id:\n{story}\n\n"
        "The person's roles (id and title) — choose the role each bullet belongs "
        "to:\n{roles}\n\n"
        "Return up to three bullets in {lang}, each citing the story id and a role id."
    ),
)


# N8's cover letters. Two prompts: the fixed paragraphs of a template (N8.3) and the
# bridge written for one application (N8.4).

LETTER_BLOCKS_V1 = Prompt(
    version="letter_blocks_v1",
    system=(
        "You write the two paragraphs that a person reuses at the top of a cover letter, "
        "in the requested language: a **presentation** of who they are and what they do, "
        "and an **achievements** paragraph saying what they have done.\n\n"
        "You may use only the material you are given: the track's bullets, the roles, "
        "the track's summary and the person's stories. Never add a number, a percentage, "
        "a year, an employer, a client or a tool that is not written in the material you "
        "cite. A number the material does not state stays unstated.\n\n"
        "Every paragraph cites the ids it draws on — bullet ids, story ids or role ids — "
        "and cites nothing else. A paragraph that cites nothing is not a paragraph.\n\n"
        "The presentation is at most 70 words. The achievements paragraph is between 80 "
        "and 160 words, one single paragraph, and leads with one flagship achievement "
        "with the numbers the material already gives for it.\n\n"
        "The voice notes say how it should read — register, formality, anything the "
        "person always wants said. Follow them, and write in {lang}."
    ),
    template=(
        "The track's bullets, in the order the track uses them:\n{bullets}\n\n"
        "The person's roles:\n{roles}\n\n"
        "The track's summary in {lang}:\n{summary}\n\n"
        "The person's stories:\n{stories}\n\n"
        "Voice notes from the person:\n{voice_notes}\n\n"
        "Return the presentation text and the achievements text, each with the ids it "
        "cites."
    ),
)


LETTER_BRIDGE_V1 = Prompt(
    version="letter_bridge_v1",
    system=(
        "You write the bridge paragraph of one cover letter — the one part written for "
        "this application and no other: why this position, and why this person fits it. "
        "You write in the posting's language.\n\n"
        "Choose the template that fits this posting from the candidates given, say why "
        "in one line, and name a runner-up only when it is genuinely close.\n\n"
        "Return three variants of the bridge, each 2 to 4 sentences and at most 90 "
        "words, each labelled with its angle in two or three words, and each taking a "
        "genuinely different angle — not three phrasings of one. Only material you are "
        "given may be used: the person's bullets, stories and roles, the posting, the "
        "company and the title. Never invent a number, a date, an employer, a tool or a "
        "company fact; a company fact is usable only with a verbatim quote from the "
        "posting, and otherwise the variant says nothing about the company.\n\n"
        "Every variant cites the ids it draws on. Do not repeat a number that appears "
        "in the chosen template's achievements paragraph: the bridge is a different "
        "achievement, not the same one twice.\n\n"
        "Also return one line of risk — what may count against this application (a "
        "sector change, a seniority gap against the title) and how to handle it — or "
        "null when nothing does."
    ),
    template=(
        "The posting:\n{posting}\n\n"
        "Company: {company}\nPosting title, exactly as stored: {title}\n\n"
        "Candidate templates (id, name, when to use it, achievements paragraph):\n"
        "{templates}\n\n"
        "The person's material, strongest evidence first:\n{material}\n\n"
        "Voice notes from the person:\n{voice_notes}\n\n"
        "Write in {lang}."
    ),
)
