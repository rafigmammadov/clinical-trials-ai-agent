# Changelog

## 1.0.0 — Finalized backend release candidate

Four internal engineering stages were implemented together as one patch; **0.7–0.9 are not claimed as independently published releases**:

- **0.7 — Planner recovery:** A rejected structured plan may receive one bounded correction, and it must pass the same grounding, recall and runtime constraints. Responses report planning attempts.
- **0.8 — Registry reliability:** Pagination tolerates isolated empty pages, detects token cycles and invalid totals, and fails on repeated non-progress.
- **0.9 — Source evidence:** Independent source-field citation auditing checks NCT IDs, exact excerpts and graph endpoint evidence. Optional guarded model evaluations measure actual plan acceptance and repair behavior, without querying the registry.
- **1.0 — Product release:** Simplified README, concise API/architecture/verification docs, removed redundant audits and interview preparation files, and required all five genuine examples during release packaging.

## Earlier development milestones

- **0.6** — Detect omitted requested filters and measure annotated filter recall.
- **0.5** — Reject invented model-generated filters before registry retrieval.
- **0.4** — Verify registered drug names and aliases, plus explicit open-ended year bounds.
- **0.3** — Response validation, request tracing, provider retries and failure injection.
- **0.2** — Record accounting, adversarial tests and reproducible archive verification.

Milestones describe engineering evolution, not a guarantee that each number was separately deployed or released. See Git tags for published version history.
