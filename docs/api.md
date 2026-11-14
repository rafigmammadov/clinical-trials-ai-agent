# API contract

The authoritative JSON Schema is generated at `GET /openapi.json` from `app/schemas/api.py`. This page explains semantics that type declarations cannot capture. The API prefix `/api/v1` is independent of the service release version.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/health` | Liveness and release version; **not** a dependency readiness probe |
| `GET` | `/api/v1/capabilities` | Supported intent and drug matching modes |
| `POST` | `/api/v1/analyze` | Validated planning, study retrieval, aggregation and chart JSON |

## Request

```json
{
  "query": "Compare trial phases for ivacaftor and lumacaftor",
  "drugs": ["ivacaftor", "lumacaftor"],
  "drug_match_mode": "registered_name",
  "max_studies": 1500,
  "citation_limit": 5
}
```

| Field | Type and constraints | Default |
|---|---|---|
| `query` | Required string, 5–2,000 non-whitespace characters | — |
| `condition` / `sponsor` | Optional nonblank strings, max 200 characters | `null` |
| `country` | Optional nonblank string, max 100 characters | `null` |
| `drugs` | Optional array of up to 3 nonblank names, each max 200 chars in the plan | `null` |
| `start_year` / `end_year` | Optional integer 1900–2100, start <= end | `null` |
| `recruiting_only` | Optional boolean overall-status restriction | `null` |
| `drug_match_mode` | `registry_text` or `registered_name` | `registry_text` |
| `max_studies` | Integer 1–5,000, **per registry search** | `1000` |
| `citation_limit` | Integer 0–50 contributing studies **per datum** | `10` |

All additional fields are rejected. A drug comparison requires exactly two distinct drugs. Other analyses accept at most one drug filter. For open-ended `since YYYY` time trends, an unspecified end year remains `null`. Named countries and other user constraints may require a typed field if the lexical validator cannot confidently interpret them.

## Success response

```text
visualization
  type             time_series | bar_chart | grouped_bar_chart | network_graph | histogram | scatter_plot
  title            human-readable title
  encoding         channel names mapped to data fields, or graph nodes and edges
  data             list of rows, or {"nodes": [...], "edges": [...]} for networks
meta
  query_plan       validated interpretation used for the request
  filters          applied search and local-filter restrictions
  source           ClinicalTrials.gov API v2
  analyzed_at      retrieval/analysis timestamp
  records_fetched  distinct upstream candidate NCT IDs
  records_used     distinct candidates surviving local filtering
  records_visualized, records_not_visualized
  total_matches    upstream candidate total when meaningful (null for two drug searches)
  cohort_matches   per-search upstream totals for two-drug comparisons
  complete         whether candidate registry retrieval completed
  visualization_truncated, visualization_total_items, visualization_items_returned
  citation_limit_per_datum, warnings, assumptions
  drug_match_mode, matched_drug_counts
  planner_attempts, planner_repaired
```

Every chart datum has `citation_count`, `citations_complete`, and a possibly capped `citations` array. Each reference includes `nct_id`, canonical `url`, `field_path`, and `excerpt`. `related_field_path` / `related_excerpt` establish additional source fields (network endpoint, drug-cohort membership, or scatter enrollment). `evidence_scope=record_identity_only` marks a record with missing source data; it is not proof that a missing field had a particular value.

A complete registry result may still have `visualization_truncated=true` when display limits suppress categories or edges. Multi-valued buckets and drug cohorts overlap; do not add their counts to infer distinct patients or trials.

## Failure responses

| Status | Meaning | Stable error name where applicable |
|---|---|---|
| `422` | Invalid JSON schema or unsupported, contradictory, invented or omitted filters | `invalid_analysis` for domain validation |
| `502` | Registry request or source response failed | `registry_unavailable` |
| `503` | Planner missing credentials, refused or failed | `planning_unavailable` |
| `500` | Internal source-citation integrity check failed | `analysis_integrity_failure` |

Every HTTP response includes `X-Request-ID` and `X-Process-Time-Ms`. Provider exception bodies, prompts and credentials are not returned in these domain errors. A 200 response still requires consumers to inspect completeness and warning metadata.

## Examples

Five saved, actual API-generated responses are linked from [README](../README.md). Live model calls can change query-plan interpretation or produce rejections; real registry counts change over time. This project does not predict medical outcomes or assess intervention efficacy.
