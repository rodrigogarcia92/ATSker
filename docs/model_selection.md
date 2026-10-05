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
