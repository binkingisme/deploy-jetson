# thresholds

Threshold table for open-set decision (FR-006, Section 14).

- `threshold_table.json` — runtime in-memory table placeholder.
  Populated **offline** by the EVT/GPD fitting pipeline (workstation).

Runtime performs **dict-only lookup** (Rule 7). Distributions are NEVER fit
at runtime.
