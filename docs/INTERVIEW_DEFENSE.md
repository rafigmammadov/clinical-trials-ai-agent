# Engineering design defense

1. **Why not ask GPT to output the chart counts?** Numeric outputs are derived from NCT records with deterministic Python aggregations; model-produced counts are not auditable.
2. **What does the LLM control?** One enumerated analysis intent and filter fields. It cannot supply API URLs, Python, SQL, or the computed chart dataset.
3. **What if the question cannot be answered?** The constrained planner has an `unsupported` intent; the use-case layer returns HTTP 422 before contacting the registry. Offline tests prove the service behavior, not the live model's classification accuracy.
4. **What does `complete` mean?** The requested registry search was fully paginated with no omitted malformed records. It does not mean every returned study appears in the chart or that the entire registry matched the intended semantic concept.
5. **How do you account for missing dates?** `records_used` reports post-filter studies, while `records_visualized` counts distinct NCT IDs actually represented. Missing/ambiguous fields are disclosed.
6. **How can phase counts exceed the number of studies?** A multi-phase trial legitimately belongs to multiple phase categories. Each NCT ID is deduplicated *within* a category, not across all categories.
7. **What is the difference between study recruitment and site recruitment?** Overall `RECRUITING` status is a study-level filter; a site listed in a country is not proof it is enrolling locally.
8. **How are network weights computed?** Each edge weight is the count of distinct studies in which the two endpoints co-occur. This is not a causal or contractual assertion.
9. **What about graph truncation?** We rank deterministically, display the top 75 edges, and expose `visualization_truncated`, eligible edge count, and supporting-study count.
10. **How do citations support an edge?** Each reference includes the NCT ID plus source paths and excerpts for both endpoints. Absent fields are labeled identity-only rather than presented as invented excerpts.
11. **How does the system withstand API failures?** Bounded requests/retries, timeouts, safe UpstreamError mapping, and tests for HTTP 429/503, malformed JSON and bad pagination.
12. **Why aren't drug names exact?** The registry search is a full-text match, not a controlled RxNorm/MeSH mapping. The response documents that limitation and avoids claims of chemical equivalence.
13. **What is your agent evaluation strategy?** A 50-case corpus measures intent and selected filter accuracy in opt-in live mode, combined with deterministic property tests for aggregation and provenance.
14. **How do you guard API secrets?** Environment variables and ignored `.env`, non-sensitive examples, source archive allowlisting, and credential-pattern checks. Prior leaked credentials must still be revoked outside the repository.
15. **What would you improve next?** First measure live planner accuracy and source-semantic errors; then prioritize entity normalization, dependency pinning, request budgets, and observability based on observed failure rates.
