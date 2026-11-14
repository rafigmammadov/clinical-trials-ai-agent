# Engineering audit

Audit date: 2026-11-14. Scope: the available source snapshot of the public `clinical-trials-ai-agent` repository, its six-page functional specification, and executable offline tests. GitHub pages were reachable, but the working container could not clone or query the Git remote directly. Verify the patch against the exact local checkout before pushing.

## Baseline evidence

- Repository layout: `app/main.py` exposes three routes; `app/agent/planner.py` implements a Pydantic-constrained OpenAI plan; `app/agent/orchestrator.py` executes the plan; `app/services/clinicaltrials.py` paginates and deduplicates; `app/services/normalizer.py` projects registry records; `app/visualizations/builder.py` produces six chart types. Source inspection, not inference from the README.
- Initial offline run: 60 tests passed on Python 3.13 in the working container. This does not establish live-model accuracy.
- The previously reported five live JSON examples were validated on the developer's Mac; these files are not present in this analysis container. They must be regenerated or validated on the receiving machine.
- CI uses Python 3.11–3.13 and runs the deterministic suite; a published Actions page showed the initial run successful. This is not a security audit of dependencies.

## Findings and remediation

| Severity | Finding | Reproduction/evidence | Resolution or remaining risk |
| --- | --- | --- | --- |
| P1 | A response could claim a complete registry result when malformed records were omitted and `totalCount` was absent. | `test_skipped_malformed_registry_record_cannot_mark_complete_without_total` failed against baseline. | `ClinicalTrialsClient.search()` now makes `complete=False` whenever a record was skipped. |
| P1 | `records_used` counted post-filter records that did not appear in the visualization. | Time-trend fixture with a missing start date: 2 filtered, 1 charted. | New `records_visualized`, `records_not_visualized`, and warnings distinguish these populations. |
| P1 | Invalid questions lacked an explicit unsupported intent, allowing a schema-valid chart plan to be produced when the request should have been rejected. | `test_unsupported_intent_does_not_call_registry` failed before implementation. | Planner's allowed schema and prompt now include `unsupported`; service returns 422 without registry access. Live recall must be measured separately. |
| P1 | Histogram/scatter accepted duplicate input records and network node labels changed with API ordering. | Permutation/duplicate metamorphic cases failed. | Builder deduplicates NCT IDs and chooses canonical node labels deterministically. |
| P2 | A known future `YYYY-MM` study start was not excluded for an unspecified end year. | `test_future_month_can_be_excluded_without_day_precision` failed. | Month-aware comparison added; same-month partial dates remain uncertain. |
| P2 | Phase comparisons silently dropped unrecognized phase labels. | `test_comparison_does_not_silently_drop_unknown_phase_category` failed. | Both cohorts now show the union of standard and observed extra phases. |
| P2 | A missing phase could be cited using only the NCT identifier without labeling its evidentiary limitations. | `test_absent_field_citation_is_explicitly_identity_only` failed. | Citations now identify `record_identity_only` rather than implicitly claiming a field excerpt. |
| P2 | Lack of a reproducible semantic-evaluation corpus. | Baseline had only scripted examples and unit tests. | 50 labeled prompts, a schema verifier, and opt-in live model scoring added under `evals/`. No live model score is claimed. |
| P2 | ZIP creation traversed complete folders without content allowlisting or credential-pattern detection. | Original `scripts/package_release.sh` used recursive `zip -r`. | Packaging now selects approved text files, checks entry paths and common credential patterns, then inspects the resulting ZIP. |
| P2 | Several provider failures and pagination layouts lacked dedicated tests. | Initial suite lacked deterministic partition-invariance and HTTP 503 exhaustion tests. | Added failure-injection and property-oriented tests. |
| P2 | API model and package dependencies have open-ended ranges. | `requirements.txt`. | Keep existing ranges for patch compatibility; lock exact verified versions in a subsequent reproducibility change. |
| P2 | Clinical term searches can include fuzzy/noncanonical matches. | `query.cond`/`query.intr` and source semantics. | Disclosed; true drug/condition ontology resolution remains unimplemented. |
| P2 | The system accepts bounded but potentially expensive queries (up to 5000 studies per cohort). | Request model, no public-facing authentication or rate limiting. | Suitable for a local evaluation service; add quotas and deployment hardening before any public production use. |
| P3 | Starlette/httpx test deprecation warning in the developer's Python 3.14 environment. | Previous test log; no warning observed in this Python 3.13 container. | Do not force incompatible dependency upgrades merely to silence it. |

## Threat model and security boundaries

The model can choose only enumerated intents and filters, not executable code, URLs, or result counts. HTTP destinations are supplied through trusted configuration, not planner output. Client-side inputs are bounded by Pydantic. A previous API key appeared in development conversation text: its issuer must revoke it; repository tests cannot verify that action. Inspect Git history separately before publishing a public repository; a clean HEAD is insufficient evidence that secrets were never committed.

Open risks: prompt-injection classification is probabilistic, not guaranteed; source query terms are not clinically canonical; registry changes can affect results between calls; network graphs and categorical charts may intentionally omit lower-frequency relationships. A complete registry search does not mean all eligible categories are displayed. The source provenance bonus is partial for missing fields and capped citations.

## Prioritized next work

1. Run the 50-case **live** planner benchmark with a rotated key; review all mismatches, not only overall accuracy.
2. Verify real trial IDs, chart bucket memberships, missing field cases, and NCT evidence links independently.
3. Verify the updated patch on the owner's Mac, refresh five live output examples, and inspect the produced ZIP.
4. Pin tested dependency versions and assess known vulnerabilities before any public production deployment.
5. Add canonical condition/drug terminology resolution and stronger resource controls only when empirical failures justify them.
