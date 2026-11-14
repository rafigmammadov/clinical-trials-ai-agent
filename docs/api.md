# HTTP API contract

The source of truth is the live OpenAPI specification at `/openapi.json` and the Pydantic models in `app/schemas/api.py`. This document records semantics that JSON Schema cannot fully express.

## Endpoints

`GET /health` returns a service-status object; it is a liveness signal, not a check that ClinicalTrials.gov or OpenAI are available. `GET /api/v1/capabilities` returns supported intent identifiers. `POST /api/v1/analyze` orchestrates the data-analysis pipeline and returns a visualization plus metadata.

Requests must be JSON objects. `query` is required and must contain 5–2,000 non-whitespace characters. Additional fields: `condition`, `sponsor`, `country` (nonblank when present); `drugs` (up to 3 nonblank names); `start_year`/`end_year` (1900–2100, ascending); `recruiting_only` (boolean); `max_studies` (1–5,000, default 1,000); `citation_limit` (0–50, default 10); `drug_match_mode` (`registry_text` by default, `registered_name` optional).

Example:

```json
{
  "query": "How many melanoma trials started each year since 2023?",
  "condition": "melanoma",
  "start_year": 2023,
  "max_studies": 1500,
  "citation_limit": 5
}
```

The full numerical response depends on the live registry; see `examples/time_trend.json` for a real saved output. The schema is stable at the top level:

```text
visualization:
  type: time_series | bar_chart | grouped_bar_chart | network_graph | histogram | scatter_plot
  title: string
  encoding: map of renderer channel definitions
  data: row array, or { nodes: [], edges: [] } for network_graph
meta:
  query_plan, filters, assumptions, warnings
  records_fetched, records_used, total_matches, complete
  records_visualized, records_not_visualized
  visualization_truncated, visualization_items_returned, visualization_total_items
  citation_limit_per_datum, analyzed_at, source, source_url
  drug_match_mode, matched_drug_counts (strict registered-name mode)
```

For ordinary charts, channel encodings use field names present in output rows. Network edges reference defined node IDs, use positive integer weights and include contributing-study provenance. Empty output is permitted and accompanied by a warning. Chart rows may represent overlapping study memberships.

## Errors and response headers

| HTTP status | Meaning |
| --- | --- |
| 200 | Analysis completed; check `meta.complete` and warnings for limitations |
| 422 | Invalid input, contradictory comparison or unsupported analysis |
| 502 | The registry failed or returned invalid data |
| 503 | Planner could not be configured or failed to produce a plan |

Request IDs and processing times are returned in `X-Request-ID` and `X-Process-Time-Ms` response headers. These are diagnostic metadata, not authentication tokens.

## Compatibility notes

This iteration adds stricter validation of existing response fields without changing the existing top-level keys. Scatter citations now contain start-date and enrollment evidence together in one NCT citation, rather than two separate citation entries for one study. Consumers that assumed exactly two entries per scatter point should use the explicit `related_field_path` and `related_excerpt` fields. This is a small, documented compatibility change.

## Registered intervention-name matching (v0.4.0)

`drug_match_mode` is a request-level choice, not an LLM-generated query-plan field. The default `registry_text` preserves the established behavior. `registered_name` verifies that a returned study explicitly lists the requested term as a registered DRUG intervention name or an `otherNames` alias. It rejects partial-string matches, other intervention kinds, and unregistered synonyms. A drug term is required or the service returns HTTP 422.

```json
{
  "query": "Compare trial phases for pembrolizumab and nivolumab",
  "drugs": ["pembrolizumab", "nivolumab"],
  "drug_match_mode": "registered_name",
  "max_studies": 1500
}
```

Strict mode sets `meta.matched_drug_counts` to post-filter cohort sizes, adds `meta.filters.drug_match_mode`, and adds drug-name/alias provenance to cited studies. For a comparison datum this is `related_field_path` plus `related_excerpt`; for other chart types this is `matched_drug_field_path` plus `matched_drug_excerpt`. Upstream `total_matches` still describes text search candidates, not verified identity matches, and matching cannot recover studies not returned by the search. See [matching semantics](intervention_identity.md).
