# Security and deployment boundaries

This is a **local analytical backend**, not an authenticated public service. Do not expose the API directly to the internet without access control, quotas, TLS termination, and monitoring. The application limits input lengths, retrieval sizes, model planning attempts, HTTP retries and rendered chart sizes; these controls alone do not provide deployment-grade abuse protection.

OpenAI credentials belong in an untracked `.env` or a secret manager. Rotate any key shared in a chat, committed to Git or exposed in an output. `.env` and local evaluation reports are Git-ignored; the release ZIP uses an allowlist and known-pattern credential scan, which cannot guarantee all secrets are absent. Review Git history separately.

The planner generates only schema-constrained filters. The backend checks invented/omitted filters before registry access and never executes model-generated code or destinations. ClinicalTrials.gov input is untrusted; source citations are validated against normalized records. Provider error bodies, credentials and user questions are not intentionally logged.

Report vulnerabilities privately to the repository maintainer; do not post keys or patient data in public issues. No formal security certification, penetration test or dependency vulnerability audit is claimed.
