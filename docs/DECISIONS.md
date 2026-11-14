# Architecture decisions and limitations

## ADR-001: One constrained planner, not a fully autonomous agent

**Decision.** Use a single structured-output LLM call to convert the user question into an allowlisted `QueryPlan`. Deterministic code translates it into ClinicalTrials.gov parameters and constructs every numeric visualization point.

**Why.** The task needs intent interpretation, not arbitrary multi-step tool autonomy. The model cannot invoke the network itself, generate Python, or manufacture counts. This reduces prompt-injection surface, makes regressions testable, and improves the fidelity of clinical source data.

**Alternative rejected.** A general ReAct loop with arbitrary tool calling: higher complexity, cost, and potential for fabricated computations for this bounded read-only analysis service.

## ADR-002: Typed boundaries with explicit exceptions

**Decision.** Pydantic validates both inbound requests and the planner's output. A normalization layer converts nested ClinicalTrials.gov records into immutable dataclasses. Errors map to HTTP 422 (unsupported query), 502 (registry failure), or 503 (planner unavailable).

**Why.** External API schemas and language-model responses must not leak unvalidated types into aggregation logic.

## ADR-003: Consistent visualization JSON contract

**Decision.** Standard visualizations use an array of row data; networks use a `data: {nodes, edges}` object. `encoding` names the exact fields a renderer should consume. Citation metadata is attached to each row, node, and edge.

**Why.** A frontend renderer can select one of six chart types without parsing model prose or guessing mapping rules.

## ADR-004: Partial results are explicitly incomplete

**Decision.** Paginate using `nextPageToken`, deduplicate using NCT ID, and cap retrieval with `max_studies`. Report `complete=false`, warning text, fetched/used counts, and registry total matches when the cap is hit. Do not extrapolate counts.

**Why.** A first-N result set returned by a relevance-ranked registry is not an unbiased sample; declaring its counts as the entire population would be misleading. Queries whose matching population exceeds the cap are best treated as exploratory previews.

### Visualization completeness is separate from registry completeness

For bounded charts, the response tracks total eligible graph edges or categories and the number displayed, plus `visualization_truncated`. Retrieval may be exhaustive (`complete=true`) while only the strongest 75 network edges or top 25 categories are shown. Warnings make the distinction explicit; omitted edges are not presented as nonexistent.

## ADR-005: Citations are bounded and honest

**Decision.** Every chart datum, node, and edge exposes NCT links, source field paths and literal supporting field values, up to a user-controlled cap. `citation_count` is the number of contributing studies, and `citations_complete` states whether the citation list covers them all.

**Why.** Full citation lists can be enormous; the cap keeps renderer payloads bounded without concealing incompleteness. Network edge citations include two exact fields (source and related target) from the same NCT record to evidence both endpoints. Read the linked NCT record to independently verify the relationship and its clinical interpretation.

## ADR-006: Conservative clinical semantics

- Start-year trends use `statusModule.startDateStruct.date`, not first-posted or update dates. Actual and estimated dates are currently combined; their type remains available in the normalized model. With an unspecified end year, known future full dates are excluded (including later dates in the current year); partial dates cannot establish day-level chronology.
- Count distinct NCT IDs per category. One study may contribute to several phases/countries/drugs, so category sums need not equal unique study count.
- `sponsor` means **lead sponsor**. The API's sponsor query also searches collaborators, so the application post-filters lead sponsor matches. This narrows records after registry retrieval.
- `recruiting_only` means overall study status `RECRUITING`; geographic views currently count countries with any site, not only recruiting sites.
- Drug search uses ClinicalTrials.gov text matching, not synonym/ontology resolution. Interventions are not guaranteed to be chemical-equivalent entities. The drug co-occurrence graph means co-listed interventions, not verified concomitant therapy.
- Enrollment may be anticipated or actual; they are combined with this distinction documented.
- Geographic aggregation from study sites does not imply active recruitment in the country.

## ADR-007: Validate the untrusted-data boundary before analysis

**Decision.** HTTP requests with blank questions or blank structured filters are
rejected, human-entered search terms are trimmed, and registry start dates are
validated as ISO `YYYY`, `YYYY-MM` or `YYYY-MM-DD` before deriving a start year.
Malformed dates become missing values rather than contaminating trend aggregations.
Tests exercise malformed values, retryable HTTP 429 responses, nonretryable provider
errors, malformed records, and repeated page tokens.

**Why.** The model and upstream registry are both external trust boundaries.
Pydantic-validated shape alone does not imply semantically valid input. A four-digit
prefix from an impossible date must not be treated as a valid historical start.

## Known limitations and next iterations

1. **Large-result completeness:** implement asynchronous bulk download, materialized aggregates, or verified `stats`/`count` endpoints for exhaustive large-population questions.
2. **Drug normalization:** canonical drug IDs (RxNorm/MeSH), synonym mapping, and distinguish arms versus combination treatments.
3. **Broader charts:** richer scatter dimensions and network edge types beyond two supported relationship families.
4. **Evidence quality:** include study date and enrollment type metadata per point, and support server-side pagination of provenance for every contributing record.
5. **Observability:** structured trace IDs, OpenTelemetry, request budgets, provider latency, and redaction-aware logging.
6. **Efficiency:** cache query plans and registry pages with careful TTL/version invalidation; monitor upstream API limits.
7. **Agent evaluation:** add a labeled corpus of natural-language queries and compare plans with expected intents/filters.
8. **Security:** authentication, per-user quotas, restrictive outbound URL allowlisting, and deployment-specific rate limiting if made public.

## Sources

- ClinicalTrials.gov Data API: https://clinicaltrials.gov/data-api/api
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- GitHub CLI repository creation: https://cli.github.com/manual/gh_repo_create
