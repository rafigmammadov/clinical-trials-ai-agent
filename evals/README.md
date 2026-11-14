# Planner evaluation

`cases.json` is a hand-labeled collection of 50 questions spanning 20 straightforward, 10 combined-filter, 5 network, 5 numerical and 10 adversarial/unsupported scenarios. Each case defines an expected intent and selected filter properties. These labels are engineering expectations, not gold-standard clinical ontology annotations.

Schema-only validation (no API key, no billable requests):

```bash
python -m evals.run --mode validate
```

Optional real model evaluation (with a rotated key in `.env`):

```bash
python -m evals.run --mode live --limit 10 --output evals/reports/planner-10.json
python -m evals.run --mode live --category adversarial --limit 10 --output evals/reports/adversarial.json
```

`--limit 10` picks two questions per family by default. Live mode submits one request per selected question and may incur API costs (and SDK retries on provider errors). Reports are ignored by Git so prompts and transcripts are not published accidentally. Failures are recorded using exception *types* rather than provider response bodies.

The reported `intent_accuracy` is exact enum agreement. `filter_accuracy` compares only annotated properties, normalizes case for strings, and treats the two drug names as an unordered pair. It is not a general clinical-semantic correctness metric; a synonym such as *diabetes mellitus type 2* versus *type 2 diabetes* may score as a mismatch. The evaluation does not retrieve clinical records or verify chart data, which are covered by separate service tests and manual source spot checks.

Do not claim live accuracy based on schema-only validation. Review individual cases before tuning prompts or changing model versions.

## Registered-name identity benchmark (offline, v0.4.0)

Run `python -m evals.identity` to test 24 hand-labeled synthetic registration examples. This is separate from the 50-question LLM planning benchmark. The test fixtures cover registered names, `otherNames` aliases, Unicode/whitespace normalization, non-drug interventions, and deliberately rejected substring/fuzzy matches. The runner is deterministic and makes **no** model or registry API calls.

A perfect 24/24 result demonstrates only that the current matching policy agrees with the annotated synthetic cases. It does not measure the recall of `query.intr`, drug ontology coverage, or the correctness of live registered records. See [intervention matching semantics](../docs/intervention_identity.md).
