# Security notes

This is an experimental analytical API, not a hardened public service. It has no authentication, per-user quotas, or abuse protection. Run it on localhost by default. Public deployment requires access controls, upstream rate-limit management, HTTPS termination, monitoring and operational review.

API keys belong in an untracked `.env` or deployment secret manager, never in Git or sample JSON. Revoke any key previously exposed in chat, screenshots, logs, commits, or other public channels. `.env` and model-evaluation reports are excluded from Git; the release ZIP uses a file allowlist and known-pattern credential scanner. A scanner cannot guarantee that every secret or historical Git commit is safe.

LLM output is validated against an explicit query-plan schema. It cannot provide arbitrary URLs, executable code or database queries. ClinicalTrials.gov fields remain untrusted data; the registry adapter normalizes or rejects invalid records. Provider failures are mapped to bounded, generic API errors without embedding raw provider response bodies.

If you find a vulnerability, contact the repository owner privately. Please avoid placing credentials or personal medical data in a public issue.
