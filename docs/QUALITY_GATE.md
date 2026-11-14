# Release quality gate

The checks below separate automated correctness from registry and clinical-semantic verification.

## Offline checks

```bash
python -m pytest -q
python -m compileall -q app tests scripts
python -m scripts.verify_examples
```

The tests use fixtures and mocked provider responses. They cover validation, malformed and partial start dates, retries, pagination, NCT deduplication, error mapping, aggregation, citations, and truncated charts. The example verifier checks saved JSON without making new provider requests.

## Live integration

With `PLANNER_MODE=openai`, a valid API key, and the server running:

```bash
bash scripts/smoke.sh
python scripts/generate_examples.py --max-studies 1500
python -m scripts.verify_examples
```

Review each saved response: `meta.query_plan`, `meta.filters`, `meta.complete`, `meta.records_used`, `meta.assumptions`, and `meta.warnings`. The registry's data changes over time, so do not rely on hard-coded expected counts.

## Semantic spot checks

- Follow several NCT citations and compare the cited fields to the chart point or network edge.
- Confirm how estimated and partial start dates affect yearly counts.
- Treat multi-phase and multi-country category sums as counts of memberships, not mutually exclusive studies.
- Do not mistake a study-wide `RECRUITING` status for a recruiting site in each listed country.
- Treat intervention text search as a name match, not a canonical drug identity.
- Distinguish complete registry retrieval from limited graph edges or categories.
- Do not infer medical outcomes, treatment efficacy, or sponsor relationships from co-listing alone.

## Release hygiene

```bash
git check-ignore .env
python -m pytest -q
python -m scripts.verify_examples
bash scripts/package_release.sh
unzip -l dist/clinical-trials-ai-agent.zip
```

Review the archive for unexpected files, local secrets, caches, and environment directories. `.env` and API credentials must not be included. An uploaded artifact should be understandable and reproducible from the README and the provided example files.
