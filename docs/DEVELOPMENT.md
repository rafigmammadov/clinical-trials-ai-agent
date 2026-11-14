# Development workflow

The service is split into separable components. Changes should target the smallest coherent component, include a test where behavior changes, and preserve the documented JSON contract.

## Component boundaries

| Component | Main path | Local checks |
| --- | --- | --- |
| HTTP layer and schemas | `app/main.py`, `app/schemas/api.py` | `tests/test_api.py`, `tests/test_schemas.py` |
| Study normalization | `app/services/normalizer.py` | `tests/test_normalizer.py` |
| Registry transport | `app/services/clinicaltrials.py` | `tests/test_client.py` |
| LLM query planning | `app/agent/planner.py` | `tests/test_service.py`, live smoke test |
| Orchestration | `app/agent/orchestrator.py` | `tests/test_service.py` |
| Visualization | `app/visualizations/builder.py` | `tests/test_charts.py` |
| Error boundaries and examples | `app/errors.py`, `scripts/verify_examples.py` | `tests/test_hardening.py`, `tests/test_example_verifier.py` |

## Running locally

```bash
source .venv/bin/activate
python -m pytest -q
python -m uvicorn app.main:app --reload
```

The local registry + model integration check is `bash scripts/smoke.sh`. A successful HTTP response is necessary but not sufficient: examine the parsed intent, filters, data accounting, and warnings.

## Debugging a bad answer

1. Look at `meta.query_plan`. Did the planner select the intended analysis and entities?
2. Compare the plan with `meta.filters`. Explicit request fields override extracted values.
3. Check `meta.records_fetched`, `meta.total_matches`, and `meta.complete` for missing pages.
4. Check `meta.records_used` and any start-date or other post-filter semantics.
5. Inspect chart encodings and the cited NCT records for the relevant data points.
6. Check `meta.visualization_truncated` separately from registry completeness.

Do not repair a faulty count by modifying an example JSON file. Fix the parser, filter, or aggregation and regenerate the example.

## Before each commit

```bash
python -m pytest -q
python -m compileall -q app tests scripts
git diff --check
git status --short
```

Use Conventional Commits to describe an actual change (`feat`, `fix`, `test`, `refactor`, `docs`, `chore`, or `ci`). Prefer one independently understandable change per commit rather than committing an arbitrary number of files. When a change genuinely affects one file, a single-file commit is appropriate.

## Before a release

```bash
python scripts/generate_examples.py --max-studies 1500
python -m scripts.verify_examples
bash scripts/package_release.sh
```

The generator requires a running service and live provider connectivity. Inspect all generated examples for semantic correctness; the verifier primarily enforces structural and numerical consistency. See [QUALITY_GATE.md](QUALITY_GATE.md).
