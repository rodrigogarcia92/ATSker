# Prompt design

ATSker calls a language model for four kinds of work: reading documents into structured data, grading how well a CV
evidences each requirement, explaining gaps that code has already found, and writing text the user asks for. Every
prompt lives in one file, [`src/extract/prompts.py`](../src/extract/prompts.py). This page explains the decisions
behind them, so you don't have to read 750 lines to see the approach.

The short version: **the prompt asks, and code enforces.** Each prompt is written to make the honest answer the easy
one, and every answer is then checked by code that does not trust the prompt.

---

## 1. Principles

**A contract, not a conversation.** Every call returns structured output against a strict JSON schema, derived from
the same Pydantic model the code parses it with (`strict_schema` in [`client.py`](../src/extract/client.py)). There is
no free-text parsing. `temperature` is always 0. A model that refuses that parameter is listed in
[`model_params.json`](../src/extract/model_params.json), so the exception is recorded as data instead of disappearing
inside the code.

**Cite or don't claim.** The model sees every bullet with an id, and any judgement above zero must name the id that
supports it. "Never cite an id you were not given" is in every prompt that cites, and the code rejects an answer that
breaks it: the call is retried once, then fails loudly.

**Make abstaining cheap.** Models fill silence. The grading rubric says it outright: *"an unsupported requirement is
level 0, which is a normal and useful answer."* Story tagging says *"if nothing fits, return an empty list"*, and story
bullets say *"fewer is better than padding."* Saying "nothing" is described as success, not failure.

**Judgement in the prompt, arithmetic in code.** The model grades evidence on a 0–3 scale and labels its basis. It
never computes a score. Weights, caps, the ceiling and every sub-score are plain Python, tested offline.

**Discover nothing you weren't asked to.** The gap prompt opens with *"You discover nothing: the gaps you are given
are the complete list."* Code finds the gaps; the model only explains them in words. This keeps one source of truth.

**Stable prefix, variable message.** The rules go in the system message, which is identical for every posting, and
only the data goes in the user message. Providers bill a cached prefix at a fraction of the price, and the split
also makes each prompt easy to read: the rules are in one place.

**Versioned like code.** Each prompt carries a version string (`evidence_grade_v4`, `summary_v5`). Changing a prompt
means a new version, and that busts the cache on purpose: answers produced under different rules are never mixed.
Old versions stay in the file, because a stored report names the prompt it was produced with, and that prompt must
still exist.

**Only what's needed leaves the machine.** Before any text is sent to a provider, e-mail addresses, phone numbers,
URLs and the user's known name are replaced with placeholders ([`redaction.py`](../src/extract/redaction.py)).

---

## 2. The prompts

| Job | Prompt (current version) | What it returns |
|---|---|---|
| Read a CV | `resume_extract_v1` | Roles, dates, bullets, education, exactly as written; never inferred or "improved" |
| Read a posting | `jd_extract_v3` | Title, requirements and tasks, using only names from the vocabulary |
| Grade the evidence | `evidence_grade_v4` | A level 0–3, a basis and a cited bullet id for each requirement |
| Recruiter search | `boolean_recall_v2` | 3–5 boolean queries a recruiter would type, broad to strict |
| Explain gaps | `gap_interpret_v1` | One plain-language note per gap that code already found |
| Match languages | `bullet_pairing_v1` | Pairs of bullets that describe the same achievement in Spanish and English |
| Tag stories | `story_suggest_v1` | Skills and ids chosen only from the lists given |
| Propose a summary | `summary_v5` | 3–4 sentences, at most 80 words, with the ids it cites |
| Rewrite a bullet | `bullet_rephrase_v1` | The same facts in the posting's words |
| Bullets from a story | `story_bullets_v1` | Up to three bullets, fewer if fewer are true |
| Cover letters | `letter_blocks_v1`, `letter_bridge_v2` | Reusable paragraphs, and one paragraph written for this application |
| Probable keywords | `keyword_infer_v1` | Keywords you could honestly add, each with its reason, labelled as probable |

---

## 3. A closer look: grading evidence

This is the prompt the score depends on most. Three choices carry it.

**Levels a recruiter would recognise.** *0 absent, 1 mentioned* (in a list, no context), *2 applied* (used in a
described task), *3 demonstrated* (with scope or an outcome). Evidence found only in the summary or the skills list is
capped at 1: *"That is how a recruiter reads a skills section: noted, not proven."*

**Transfer without inflation.** Each grade also has a basis: *direct*, *equivalent* (a tool that swaps in weeks, one hop
only, and only from a family listed as data) or *transferable* (the same problem solved elsewhere). Transfer must pass
a three-question domain test: the domain is the setting rather than the skill itself, each core task has a matching
CV task, and the gap is learnable in three months. Regulated and certification-gated fields fail the third question.
One sentence guards the result: *"Transfer never becomes a claim … Never name the posting's tool as theirs because it
was credited as an equivalent."*

**Equivalence is data.** Version 4 differs from version 3 in one way: the list of tool families (for example, BI tools)
is injected from the database instead of being left to the model's judgement. The same table backs a check in code, so
the prompt and the code agree on what counts as equivalent.

---

## 4. Iterating: the summary, v1 to v5

The summary generator shows how the prompts were refined against real output.

| Version | Change | Why |
|---|---|---|
| v1–v2 | Summary plus a skills list | v2 stated the skills rule outright, so the user's skill pool stopped being treated as a suggestion |
| v3 | The summary alone | The skills list moved to its own Keywords card; the pool stays in the message only as context, never as output |
| v4 | Three ordered rules | Open with the posting's title, word for word; name 3–4 skills from a shortlist that code chose; follow and improve the user's own summary, keeping its voice and facts |
| v5 | Two sentences added to v4 | Cite the bullet that shows each skill named; drop a skill from the old summary that isn't on the shortlist instead of keeping it |

Each step was driven by output that broke a rule, not by taste. Every version stays defined in the file, because a
saved proposal names the version that wrote it.

---

## 5. The backstop: code that doesn't trust the prompt

A prompt makes the right answer likely. It can't make it certain, so every generated sentence passes three validators
([`validators.py`](../src/generate/validators.py)) before the user sees it:

1. **Provenance:** it cites a stored bullet, story or summary.
2. **Literal preservation:** every number, date and proper noun in it exists in the cited source.
3. **Skill closure:** every skill it names is in the user's own data, and a summary's prose names only skills evidenced
   at level 2 or higher.

A banned-phrase list ([`banned_phrases.json`](../src/generate/banned_phrases.json): "passionate about", "synergy",
"me apasiona") is sent with the generation prompts, and a cover letter that uses one anyway is flagged in code. Probable keywords are re-checked against the user's
material by `validate_keyword_items`, and the interface labels them *"Probable — only if true."*

---

## 6. Running the prompts across models

The same prompts run on Gemini 3.8 Flash (the private app) and Claude Haiku 5.5 (the public demo, in progress). The
model is chosen by experiment: agreement with labelled pairs, stability over repeated runs, invented citations, cost
and latency (see [`methodology.md`](methodology.md)). Because prompts are versioned and every call is logged with its
version, model, tokens, cost and latency, a model change can be compared on the same inputs.
