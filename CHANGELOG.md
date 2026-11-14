# Changelog

## v0.4.0 — Registered intervention evidence (candidate, not a published release)

- Add opt-in `drug_match_mode=registered_name` for registered DRUG name or `otherNames` alias verification after registry candidate search. Preserve `registry_text` as the default.
- Report verified post-filter cohort sizes in `meta.matched_drug_counts` and expose the selected matching mode separately from LLM-generated query plans.
- Attach registered name/alias evidence to strict cohort citations in comparisons and other chart families.
- Add 24 synthetic, hand-labeled terminology evaluation cases and focused integration regressions. The benchmark does not measure live clinical ontology accuracy.
- Add explicit documentation for candidate-retrieval limitations, synonyms, overlapping cohorts, and source evidence.
- Add `--strict-comparison` to the real-example generator without changing its default output behavior.


## Unreleased — reliability and contract improvements

- Reuse the OpenAI planner's HTTP connection pool across application requests; close it on shutdown.
- Add generated request IDs, elapsed-time response headers and privacy-aware request telemetry.
- Validate chart encoding fields, graph node references and response-record accounting.
- Change enrollment-scatter citations to carry both required source fields in a single study citation.
- Honor HTTP-date `Retry-After` headers and retry HTTP 408 responses with bounded delays.
- Reject invalid registry timeouts and misconfigured non-HTTPS external endpoints at startup.
- Extend live planner evaluation reports with category-level intent and filter metrics.
- Add regression tests for those behaviors and expand the API, architecture and security documentation.

This section describes changes prepared in the current working tree. It is not a claim that a GitHub release or PyPI package has been published.
