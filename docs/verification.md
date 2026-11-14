# Verification and release procedure

## Offline quality gates

```bash
python -m compileall -q app tests scripts evals
python -m pytest -q
python -m evals.run --mode validate
python -m evals.identity
python -m evals.grounding
python -m evals.recall
```

The pytest suite uses synthetic source fixtures and HTTP mocks for negative inputs, partial pagination, retries, deduplication, graph semantics, citation source-field consistency, plan repair and upstream failures. Benchmark fixtures are **not live accuracy claims**: identity (24 labels), grounding (54 labels), recall (74 labels), and planner format (50 questions) are evaluated independently.

## Live checks (requires a private configured API key)

Start `python -m uvicorn app.main:app --reload` in one terminal. In another:

```bash
bash scripts/smoke.sh
python scripts/generate_examples.py --max-studies 1500 --strict-comparison
python -m scripts.verify_examples
```

`smoke.sh` deliberately queries only 50 studies; its `complete=false` response is expected for larger cohorts. The generated examples should be registry complete according to the metadata validator. The network example may display a truncated graph, independent of candidate retrieval completeness. Inspect example query plans and sample source NCT records manually before submission.

Optional **billable** model evaluations:

```bash
python -m evals.run --mode live --limit 10 --output evals/reports/planner.json
python -m evals.run --mode guarded --limit 10 --output evals/reports/guarded.json
```

`live` measures schema validity, intent agreement and annotated filter extraction; `guarded` runs the actual deterministic plan validation and at most one correction (no clinical registry calls). Neither metric measures medical outcomes or search recall. Reports are `.gitignore`d to avoid inadvertently sharing private model transcripts.

## Release

```bash
bash scripts/package_release.sh
python -m scripts.audit_archive --inspect dist/clinical-trials-ai-agent.zip
unzip -l dist/clinical-trials-ai-agent.zip
```

Packaging requires five genuine, schema-validated example outputs and an explicit source allowlist; it refuses a tracked `.env` and scans for known credential signatures. No scanner can prove all secrets or dependency vulnerabilities are absent. Check `git status`, review the ZIP and rotate any previously disclosed key before publishing.

The original assignment requires source code, how to run, documented request/response schema, design decisions, limits and 3–5 actual query/JSON output pairs; optional frontend is not required. AI use and validation must be disclosed. The project deliberately retains all five live example JSONs and the four JSON benchmark corpora—none are redundant to its tests or required examples.
