"""Ingest (PRD F2): an upload becomes a reviewed draft, then a merged master record.

This package is composition, like `analysis.py`: it imports `parse/` and `extract/`
and never the other way around, so the deterministic core stays offline-testable.

* `documents` — bytes and a filename in, text and a gate report out.
* `draft` — the model's extraction normalised: dates, skills, and the deterministic
  education/certification split.
* `merge` — the F2.5 diff (new / changed / unchanged) and the merge that writes it.
"""