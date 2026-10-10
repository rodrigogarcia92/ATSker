# Methodology: how ATSker scores a CV

This document explains how ATSker computes its numbers, how it checks them, and where those checks are weak. The README makes claims; this page is where they are defined and where their limits are stated.

Identifiers such as F5.4 in code comments refer to an internal specification; the rules that matter are summarised here.

## 1. What is scored, and why

ATSker answers one question for one CV and one job posting: how well does this CV fit what this posting asks for, judged the way an applicant-tracking system (ATS) and a recruiter would read it. Job Match is a number from 0 to 100. It is not a prediction of whether someone will be hired, and it is not a verdict on the candidate.

Three rules shape the design.

- **The model appears only at the edges.** A language model turns a posting into structured requirements, grades the CV's evidence against them, and writes text when asked. Everything in between (normalisation, scoring, the readability gate, the recruiter searches, the gap list) is ordinary code that returns the same output for the same input.
- **Every number traces to a rule and a source.** Each sub-score lists the terms it found and the ones it missed. Each evidence grade cites a bullet the user wrote.
- **A higher score is never a reason to add a claim.** Generated text may use only skills and facts the user's own material contains. Anything missing goes into the gap list, never into the CV.

## 2. Job Match

Job Match is a weighted sum of four sub-scores (weight set `w4`):

| Sub-score | Weight | What it measures |
|---|---|---|
| Skills | 0.40 | Each requirement graded 0–3 from the CV, credited by how the evidence transfers |
| Experience | 0.25 | Years a recruiter would count for this posting, plus its core tasks already done |
| Title | 0.20 | Overlap between the posting's title and the CV's titles |
| Keywords | 0.15 | The posting's own terms found in the CV text |

`Job Match = round(100 × (0.40·Skills + 0.25·Experience + 0.20·Title + 0.15·Keywords))`, then capped by the readability gate (§4).

The weights are a starting point. The development split (§7) is the only data allowed to move them, and every change creates a new weight-set version. Each report records the version and a hash of the values, so a stored score can always be traced to the configuration that produced it.

### 2.1 Skills: level, basis and credit

Each requirement the posting states is graded on a four-level scale:

| Level | Meaning |
|---|---|
| 0 | Absent |
| 1 | Mentioned only: appears in a skills list, with no context |
| 2 | Applied: used in a described task |
| 3 | Demonstrated: used, with scope or outcome attached |

The grader also records the basis of the evidence, and each basis earns a credit:

| Basis | Credit | Example |
|---|---|---|
| `direct` | 1.00 | Power BI asked for, Power BI in a bullet |
| `equivalent` | 0.75 | Tableau asked for, Power BI evidenced (same family of tools) |
| `transferable` | 0.50 | Master-data management asked for, reference-data governance evidenced |
| `none` | 0 | Not evidenced |

A requirement contributes `level / 3 × credit`, weighted 0.75 if it is a must-have and 0.25 if it is a nice-to-have. The Skills score is shown split into the part resting on direct evidence and the part resting on transfer, so the user can see how much of the number depends on an argument.

Several rules keep the grader honest.

- A requirement graded above zero must cite a bullet the user wrote. A citation to an identifier the model was never given is a schema failure: the grader retries once, and if the retry also fails, the analysis fails loudly.
- Evidence found only in the summary or the skills list is capped at level 1. A skills list can be noted but does not prove a skill.
- Equivalence is one hop, and it comes from family data (a group label on each skill, reviewed by hand), not from the model's memory. Code confirms or downgrades an equivalence the model proposes. A tool that no family confirms is downgraded to `transferable`.
- Transfer is credited only when the domain passes three tests: the posting names the domain as the setting of the work rather than the skill the job consists of; each core task matches a task in the CV that produces the same kind of deliverable; and the missing domain knowledge is learnable within about three months. Regulated, certification-gated and deep-specialist domains fail the third test.

Transfer changes how much a requirement counts. It never changes what the user sends: a generated summary cannot name a tool because that tool was credited as an equivalent.

### 2.2 Experience

`Experience = 0.6 × years part + 0.4 × task coverage`

- **Years part.** A role is *relevant* when one of its bullets is cited at level 2 or higher for a `direct` or `equivalent` requirement or task (the role counts in full), or only for a `transferable` one (it counts half). Relevant years are the years of fully relevant roles plus half the extra years that half-relevant roles add. The years part is 1 minus 0.25 for each year the CV falls short of the years the posting requires, floored at 0. If the posting states no years, the years part is 1.0 with one relevant year, and lower below that.
- **Task coverage.** The posting's core tasks (at most eight) are graded with the same levels and citation rules. Coverage is the sum of levels divided by 3 × the number of tasks. A task can be evidenced only by a bullet, not by the summary or skills list.

Roles whose bullets are not in the chosen track cannot be cited, so they do not count. The track decides what evidence exists, as it does for Skills. If the posting lists no tasks, Experience is the years part alone, and the report says so.

### 2.3 Title

Title is word overlap between the posting's title and the track's headline and role titles, after alias expansion and removal of Spanish and English function words (*de, del, la, el, y, of, the, and*). Seniority does not enter the score in either direction. When the seniority the posting asks for differs from the seniority in the user's most recent title, a separate alert is shown beside the score, because that gap matters for fit and salary, not for word overlap.

### 2.4 Keywords

Keywords are scored with BM25 over every term the posting asks for (must-haves, nice-to-haves and any other term the extractor finds), de-duplicated through the alias map and normalised against the highest score those terms could reach. The match is literal on purpose. Aliases count (`Power-BI`, `PowerBI` and `Power BI` are one term). Equivalents do not: Tableau is not Power BI for this purpose. A real applicant-tracking filter does not know that two tools do the same job, and the report says so.

## 3. The ceiling

The ceiling is the best Job Match the user's own material could reach for this posting. It separates what editing can fix from what needs material the record does not contain. The remaining points are attributed to causes: experience ATSker has no record of, years of experience, title, keywords that are not in the material, and stronger evidence on requirements the CV already covers. The ceiling is an estimate, and it is labelled as one.

## 4. The readability gate

Before content is scored, the CV file goes through deterministic checks on its layout. For PDFs, the checks use word-level geometry from `pdfplumber`:

| Check | Severity |
|---|---|
| No extractable text | Blocker |
| Contact details in the header or footer | Blocker |
| Text inside a table | Blocker |
| Hidden text containing letters or digits | Blocker |
| Hidden characters with no letters or digits (spacers, separators) | Information, or warning past a small limit |
| Multi-column body (a gutter of 40 pt or more across 60% of the page) | Warning |
| No recognisable section headings | Warning |
| Mojibake (broken character encoding) | Warning |
| Image-based bullets | Information |
| Non-embedded fonts | Information |

**Gate arithmetic:** any blocker caps Job Match at 40, and any warning caps it at 85. The uncapped score is always shown beside the capped one, so the user sees what fixing the layout would earn.

Hidden text is classified by what the hidden characters are, not how many there are. A hidden word that contains letters or digits is a blocker, because real words hidden from the reader are exactly what the check exists to catch. Hidden characters that carry no letter or digit, such as a white spacer or a stray punctuation mark left by a template, are reported as information and cap nothing, as long as they stay within a small limit.

Word files receive only the checks that a `.docx` can support. The report names the checks that did not run for that format, so a clean result cannot be mistaken for a complete one.

## 5. Recruiter-search recall

Recruiters find candidates with boolean searches on applicant-tracking systems and job boards. ATSker derives three to five searches a recruiter would plausibly run, ordered broadest to narrowest, as flat queries of AND-ed OR-groups with exclusions. Each query is evaluated in code against the track's text (bullets, skills, headline, summary, titles, education and certifications), with aliases expanded. The report shows pass or fail, the clause that failed, and the bullet that satisfied each clause that passed. Each query is also written out as a string the user can paste into a job board.

Recall is a **gate, not a score**. It sits beside Job Match and does not change it, because a missing term is not a percentage. The search runs against the track's text, not against a live profile, which makes it a proxy.

## 6. Generated text

The model may propose a summary, a cover-letter paragraph or a rephrased bullet. Every proposal must pass three validators before it is shown:

1. **Provenance.** Every output sentence maps to a stored bullet, story or summary.
2. **Literal preservation.** Every number, date and proper noun in the output also appears in the cited source. This is what stops a long story from turning into a bullet with an invented metric.
3. **Skill closure.** Every skill named is one the user has. A skill named in a summary must be evidenced at level 2 or higher in the selected bullets, or be named in the base summary the proposal cites.

Failures are shown with the offending text highlighted. They are never silently dropped and never silently shipped. A separate style check rejects a fixed list of stock phrases, in English and Spanish, such as "I am excited to" or "leverage". One retry is allowed, and the retry is told which rule failed. A proposal is a reviewable diff, and nothing is written to the CV without the user's acceptance.

## 7. Evaluation

Scores are judged by **rank order**, not by absolute value. Sixteen labelled (CV, posting) pairs were bucketed as *strong*, *plausible* or *stretch*. Twelve form the **development split**, used to design the scorer. Four form the **test split**. The primary statistic is Kendall's τ-b, with Spearman's ρ reported alongside. Intervals come from 2,000 bootstrap resamples.

Results on the development split, for the frozen `w4` configuration:

| Metric | Value | 95% interval |
|---|---|---|
| Kendall τ-b | 0.646 | [0.223, 0.948] |
| Spearman ρ | 0.747 | [0.254, 0.978] |

The gate declared before the evaluation was ρ ≥ 0.7 at n = 12. The point estimate passes it, but the interval runs from weak to strong agreement. Trust the ranking more than the number.

**Ablation.** Each sub-score was dropped in turn, and τ-b was re-measured:

| Sub-score dropped | τ-b |
|---|---|
| None (full `w4`) | 0.646 |
| Experience | 0.497 |
| Title | 0.593 |
| Skills | 0.657 |
| Keywords | 0.657 |

Dropping Experience or Title lowers agreement. Dropping Skills or Keywords does not, at this sample size. That is not proof they are decoration: the sample is too small to separate them, so they will be re-measured as the set grows.

**Labels** come from three kinds of rater, each recorded with the pair: the author, labelling blind before running anything; a versioned blind LLM rater; and, where one could be found, a human recruiter. Two caveats apply.

- The LLM rater and the grader share one definition of transfer. Agreement with the rater partly reflects that shared rubric. It is not evidence that recruiters agree.
- **The test split is no longer blind.** The author scored the four test pairs by hand under `w3` (2026-09-24) and again under `w4` (2026-09-26). Nothing has been tuned on them since, but they cannot now confirm the frozen version. The remedy is planned: at least 20 pairs, labelled blind before any scoring, with at least four kept sealed as test.

**Judge stability** is measured separately. Repeated gradings of the same analysis run with the answer cache bypassed, so the measurement is of the judge and not of the cache. A test fails if that bypass is ever removed. The band within which two gradings count as "no significant change" is provisional at 5 points until it is measured on stored analyses.

**Isolation** is tested: a user who asks for another user's record by identifier receives a 404 response, not a 403.

## 8. Model selection

The model that grades evidence was chosen by an experiment, not by preference. Candidates were compared on:

- rank agreement with the labelled pairs;
- stability across repeated runs with the cache bypassed;
- invented citations, meaning a cited bullet identifier that was never given;
- latency on the same posting;
- cost per analysis, from a ledger of model tokens.

| Candidate | Outcome |
|---|---|
| **Gemini 3.8 Flash, low reasoning** | **Default.** No invented citations in the bench runs. |
| DeepSeek V4.1 Flash, max reasoning | Ruled out: timed out at 300 seconds. |
| GPT-6 Luna, max reasoning | Ruled out: cited an invented bullet on both grading attempts in the stability run, and did not finish an analysis within 300 seconds. |
| GPT-6.1 Sol | Trialled on 2026-09-30 against the replacement rule: higher development agreement beyond the intervals, no worse stability, and cost at or below $0.02 per analysis. Gemini stayed the default. |
| Claude Haiku 5.5, low reasoning | Side by side on the same postings (2026-10-08): about 3.4 times cheaper per analysis on the ledger and close in quality, with no reliability failure recorded, but slower. Gemini stayed the default; the search for a faster model for a planned free public demo continues. |

A **latency bench**, kept outside the repository, timed JD extraction and evidence grading on one posting, with medians over three runs at low reasoning. Its latest round:

| Model | Median time | Median cost | Invented citations | CV used |
|---|---|---|---|---|
| Gemini 3.5 Flash-Lite | 17.1 s | $0.0057 | 0 | Standard |
| Gemini 3.8 Flash | 22.3 s | $0.0100 | 0 | Standard |
| Claude Haiku 5.5 | 25.7 s | $0.0026 | 0 | Strict (generalised) |

The bench has no labelled reference, so it measures speed, cost and citation validity, not agreement with labels. It works as a first filter. Shortlisted models are then compared side by side in the application. The Haiku row uses a different, generalised CV; on the standard CV, two of its three runs failed on network errors, so its standard-CV time rests on a single run and is not in the table.

Cost, for reference: one measured analysis of the private app cost about $0.016 at Gemini's promotional output price. The budget for the runtime model is at most $0.02 per single-track analysis at list prices. Evaluation runs may use any model.

## 9. Privacy

- Names, e-mail addresses, phone numbers and web addresses are replaced with placeholders before any text leaves for a model provider. Names the user has entered are removed too.
- Logs hold hashes and identifiers only. They never contain CV text, story bodies or posting text.
- Readability findings report page numbers, counts and bounding boxes, never the matched text. The interface reads the characters on demand from the stored original, inside the user's own session, and stores them nowhere.
- Every data query is scoped to the signed-in user. The user identifier comes from the session, never from a URL or a form field.
- Deleting an item removes it permanently. Deleting everything blanks the stored model answers that contain personal content, and keeps token counts and cost, so the cost ledger stays accurate.
- **Stated trade-off:** career data is stored on managed infrastructure in the United States and passes through a third-party model provider.

## 10. Known limitations

- **Small evaluation set.** Twelve development pairs and four test pairs. Intervals are wide.
- **The test split has been seen** (§7). Its results cannot confirm the frozen configuration until the planned extension is done.
- **The rater shares the grader's rubric** for transfer (§7).
- **The keyword and search screens are literal by design.** They under-credit real equivalents, as a machine filter would.
- **Recruiter search is a proxy.** It is checked against the track's text, not against a live profile.
- **Title is language-sensitive.** A Spanish title against an English posting scores lower, because an ATS matches the words sent. The report says when this happens.
- **Weights and splits are starting points.** The basis credits, the 0.6 / 0.4 Experience split and the stability band may move with more data.
- **Job Match measures fit, not the probability of being hired.** No outcome data exists yet, so the score has not been validated against interviews.
- **The readability gate is partial for Word files,** and the report says which checks did not run.
- **The ceiling is an estimate.**

## 11. Decision log

| Date | Decision | Evidence |
|---|---|---|
| 2026-09-19 | First cost measurement: about $0.001–0.007 per analysis | Cost ledger at the time |
| 2026-09-20 | Upload-first design; semantic similarity removed; four sub-scores | A clean CV was capped at 40 because two hidden punctuation glyphs were treated as hidden words. Fixed by classifying hidden characters by content (§4). |
| 2026-09-22 | Basis credits 1.00 / 0.75 / 0.50; the grader reads the summary and skills list; unsupported claims capped at level 1 | Rubric change, frozen as `w3` before its test split was first read on 2026-09-24 |
| 2026-09-24 | `w4`: title without seniority; equivalents from family data; every posting term counted as a keyword | Found on the development split: title penalised a matching title, and tool equivalents were missed |
| 2026-09-25 | Experience redesigned around relevant years and core tasks; boolean queries made flat; runtime cap of $0.02 per analysis amended, with evaluation runs exempt | Under `w3`, Experience was 1.00 on all 16 pairs, so it did not discriminate |
| 2026-09-26 | Test pairs scored by hand under `w4`; no further tuning on them | Test split no longer blind (§7) |
| 2026-09-30 | GPT-6.1 Sol trialled; Gemini 3.8 Flash (low) kept as default | Replacement rule in the evaluation runbook |
| 2026-10-03 | Model testing closed; Gemini 3.8 Flash (low) confirmed | DeepSeek V4.1 Flash timed out; GPT-6 Luna cited an invented bullet |
| 2026-10-08 | Claude Haiku 5.5 side by side; Gemini kept as default | About 3.4× cheaper per analysis on the ledger, but slower; latency bench, round 2 |
