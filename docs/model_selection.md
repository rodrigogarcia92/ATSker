# Model selection

Results of the model experiments (PRD §7: *model selection is an experiment, not a
preference*). Newest section last.

## 2026-10-03 (final)

Model testing is closed. The decision:

- **Gemini 3.8 Flash at low reasoning stays.** It is the model the app runs on.
- **DeepSeek V4.1 Flash at max** timed out at 300 s.
- **GPT-6 Luna at max** raised `CitationViolation` (an invented bullet id) on both grading
  tries in the stability run, and did not finish an analysis within 300 s in the
  side-by-side test.

No further candidate is being run; the scorer's w4 weights, the vocabulary and the model and
reasoning settings are unchanged.

## 2026-10-08 — Haiku 5.5 side-by-side: Gemini stays

Run as a side-by-side on dev, not on prod: two local instances on the same dev database, Gemini 3.8 Flash
`low` on one port and `anthropic/claude-haiku-5.5` on the other, the same postings in both (the method of the
2026-10-03 Luna test). Ledger (`llm_costs.py summary`): an analysis (extraction, grading, gaps, recruiter
queries) cost about **$0.0048 under Haiku against $0.0164 under Gemini** (≈ 3.4× cheaper; Gemini at its
promotional output price); a summary proposal $0.0007 against $0.0031; a keyword inference $0.0006 against
$0.0102. Haiku used more tokens per call (≈ 1.7× prompt, ≈ 2× completion in grading) and still cost less.
Quality: close to Gemini, with no reliability failure recorded. **It was slower**, by an amount the ledger
could not show (it had no latency; one Gemini posting was partly answered from cache, which also flatters
Gemini's time). Decision (author): **Gemini 3.8 Flash `low` stays the default** for the private app; the
search for a faster model, for the planned free demo, continues, with latency as a first-class criterion.

The ledger (development calls, model names and tokens only):

```
model                      purpose             calls purged  prompt tok  compl tok         cost    avg/call
anthropic/claude-haiku-5.5 boolean_queries         2      0        4854       1199    $0.001085   $0.000542
anthropic/claude-haiku-5.5 evidence_grade          2      0        9409       6660    $0.004271   $0.002136
anthropic/claude-haiku-5.5 gap_interpret           2      0        5570       2680    $0.001897   $0.000948
anthropic/claude-haiku-5.5 generate_summary        2      0        8011       1177    $0.001390   $0.000695
anthropic/claude-haiku-5.5 jd_extract              2      0        5466       3785    $0.002439   $0.001220
anthropic/claude-haiku-5.5 keyword_infer           1      0        3787        405    $0.000581   $0.000581
google/gemini-3.8-flash    boolean_queries         1      0        1412        261    $0.002038   $0.002038
google/gemini-3.8-flash    evidence_grade          1      0        3260       1441    $0.007849   $0.007849
google/gemini-3.8-flash    gap_interpret           1      0        1634        591    $0.003442   $0.003442
google/gemini-3.8-flash    generate_summary        2      0        5583        527    $0.006164   $0.003082
google/gemini-3.8-flash    jd_extract              1      0        1726        472    $0.003065   $0.003065
google/gemini-3.8-flash    keyword_infer           1      0        2674       2185    $0.010199   $0.010199

anthropic/claude-haiku-5.5 (all purposes)         11      0       37097      15906    $0.011663   $0.001060
google/gemini-3.8-flash    (all purposes)          7      0       16289       5477    $0.032757   $0.004680
```

- Haiku ran two analyses and Gemini one (the other posting's Gemini analysis came from the cache), so compare per analysis, not totals.
- Latency was not recorded in this ledger; each call now stores it (`llm_calls.latency_ms`).
