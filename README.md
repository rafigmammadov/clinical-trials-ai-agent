# Clinical Trials AI Agent

A Python service that translates natural-language questions about clinical studies into chart-ready JSON. It uses an LLM to interpret the question, retrieves study records from ClinicalTrials.gov, and computes visualizations from those records rather than asking the model to produce numbers.

The API returns chart encodings, aggregated data, NCT-level evidence, and metadata about how much of the matching dataset was retrieved. There is no frontend; any renderer that understands the response contract can consume the output.

## How it works

```text
POST /api/v1/analyze
        |
        v
Pydantic request validation
        |
        v
OpenAI planner -> constrained QueryPlan
        |
        v
ClinicalTrials.gov v2 client -> pagination, retries, NCT deduplication
        |
        v
Study normalization -> local filter checks
        |
        v
Deterministic aggregation -> visualization specification + citations
        |
        v
Pydantic response validation -> JSON
```

The model selects an allowed analysis intent and extracts filters. It cannot execute generated code, choose arbitrary network destinations, or fabricate the values in the response. A limited rule-based planner is available for local smoke tests, but it is not equivalent to the LLM planner.

## Getting started

Requirements: Python 3.11 or newer, internet access to ClinicalTrials.gov, and an OpenAI API key for natural-language planning. The registry itself does not require an API key.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`, keep `PLANNER_MODE=openai`, and choose an allowed model (default: `gpt-4.1-mini`). Do not commit `.env` or copy real credentials into examples or logs. If a key has been exposed, revoke it and use a replacement.

Start the API:

```bash
python -m uvicorn app.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for the generated OpenAPI interface. Other endpoints:

- `GET /health` — liveness check
- `GET /api/v1/capabilities` — supported query intents
- `POST /api/v1/analyze` — plan, retrieve, aggregate, and return a visualization

### Example request

```bash
curl --fail-with-body -sS http://127.0.0.1:8000/api/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "How have melanoma clinical trial starts changed each year since 2023?",
    "condition": "melanoma",
    "start_year": 2023,
    "max_studies": 1500,
    "citation_limit": 5
  }' > /tmp/clinical-trials-response.json

python -m json.tool /tmp/clinical-trials-response.json
```

`query` is required. Structured fields are optional and override the corresponding filters inferred by the model. The request also accepts `drugs` (up to three, or exactly two for a comparison), `sponsor`, `country`, `end_year`, `recruiting_only`, `max_studies` (1–5000 per registry search), and `citation_limit` (0–50). See `/docs` and `app/schemas/api.py` for validation constraints.

### Response contract

The response has two top-level objects:

- `visualization`: a chart `type`, `title`, renderer `encoding`, and `data`. Ordinary charts use a row array; networks use `{ "nodes": [...], "edges": [...] }`.
- `meta`: the interpreted query plan, applied filters, retrieval counts, completeness, assumptions, warnings, and citation limits.

Each populated chart row or graph relationship can contain supporting NCT IDs, links to the official study record, field paths, and excerpts. To keep responses bounded, citations can be capped. `citation_count` records the number of contributing studies; `citations_complete` indicates whether the response includes all their citations.

Treat `meta.complete` and `meta.visualization_truncated` separately. The former describes registry retrieval; the latter indicates that the renderer-facing chart omits lower-ranked categories or graph edges. A full registry result can still produce a truncated graph.

## Supported analyses

| Intent | JSON visualization | Calculation |
| --- | --- | --- |
| `time_trend` | `time_series` | Distinct studies grouped by start year |
| `phase_distribution` | `bar_chart` | Study counts per phase |
| `intervention_distribution` | `bar_chart` | Study counts per intervention type |
| `status_distribution` | `bar_chart` | Study counts per overall status |
| `sponsor_distribution` | `bar_chart` | Study counts per lead sponsor |
| `geography` | `bar_chart` | Distinct studies with a listed site in each country |
| `drug_comparison` | `grouped_bar_chart` | Phase distribution for two independently searched drug cohorts |
| `sponsor_drug_network` | `network_graph` | Co-occurrence of lead sponsor and registered drug intervention |
| `drug_cooccurrence_network` | `network_graph` | Drug interventions co-listed in the same study |
| `enrollment_histogram` | `histogram` | Enrollment counts binned into ranges |
| `enrollment_scatter` | `scatter_plot` | Study start year against enrollment count |

The chart builder is deterministic and does not use the LLM to compute counts. Study IDs are deduplicated within each category. A multi-phase or multinational study may contribute to multiple categories, so category totals can exceed the number of distinct studies. Two drug cohorts can overlap.

## Correctness boundaries

These are deliberate semantics, not guarantees of complete clinical interpretation:

- Registry searches for drugs use text matching, not RxNorm or another canonical drug ontology. A matching intervention name is not proof of pharmacological equivalence.
- `recruiting_only` filters the study's overall status. A listed study site in a country is not necessarily recruiting locally.
- Start-year trends use the study start-date field. Missing or invalid dates are excluded; partial and estimated dates cannot establish precise start timing. Known future full dates are excluded when no end year is supplied.
- Enrollment can be anticipated or actual. The current aggregations do not split those types.
- A network edge records co-listing within registry records, not a causal, contractual, or treatment relationship.
- Queries exceeding `max_studies` return explicitly incomplete results. Network graphs and some categorical charts may additionally limit rendered items, with independent warnings.

Do not interpret the JSON as medical advice or as a complete population count when `meta.complete` is false. For field-level definitions and tradeoffs, see [architecture decisions](docs/DECISIONS.md).

## Tests and reproducibility

The default tests are offline: they use mocked API interactions and fixtures rather than billing an LLM account or requiring network access.

```bash
python -m pytest -q
python -m compileall -q app tests scripts
```

The test suite covers parsing, validation, pagination, deduplication, HTTP retries, malformed records, aggregation, citations, truncation, error mapping, and a mocked API request. CI runs it on Python 3.11, 3.12, and 3.13. A passing offline suite does not replace a live registry and model smoke test.

With the server running and `PLANNER_MODE=openai`:

```bash
bash scripts/smoke.sh
python scripts/generate_examples.py --max-studies 1500
python -m scripts.verify_examples
```

The generator writes five registry-backed responses to `examples/` for time trends, phases, geography, sponsor–drug networks, and drug comparisons. Actual counts change as the registry is updated. The verifier checks structural consistency, chart accounting, citation references, and completeness metadata using the saved files; it makes no provider calls.

For an offline plumbing check, use `PLANNER_MODE=rules` and pass explicit structured filters. Restart the server after changing `.env`.

## Code layout

```text
app/
  agent/           structured planning and orchestration
  schemas/         HTTP request, query plan, and visualization types
  services/        registry HTTP client and study normalization
  visualizations/  deterministic aggregations and evidence attachment
  config.py        environment-backed configuration
  main.py          FastAPI application and exception mapping
tests/             offline unit and API contract tests
examples/          saved live JSON responses
scripts/           setup, smoke checks, example validation, release archive
docs/              design decisions and quality checks
```

The HTTP layer does not contain analysis rules. The planner, registry client, normalizer, and visualization builder can be tested independently. Provider failures are mapped to stable HTTP errors (`422` for invalid analyses, `502` for registry failures, and `503` for planning failures).

## Development

Changes use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) such as `feat(agent): ...`, `fix(data): ...`, `test(charts): ...`, and `docs: ...`. Run the tests before pushing changes. See [development workflow](docs/DEVELOPMENT.md) and [release checks](docs/QUALITY_GATE.md).

To build a source archive after generating and validating the examples:

```bash
bash scripts/package_release.sh
```

The archive is written to `dist/clinical-trials-ai-agent.zip`. The script excludes the local environment and runs the quality checks before packaging. Review the archive contents and keep all API keys outside Git.

## References

- [ClinicalTrials.gov Data API](https://clinicaltrials.gov/data-api/api)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
