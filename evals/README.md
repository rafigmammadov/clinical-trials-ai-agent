# Planning evaluations

The `evals/` directory contains four **hand-labeled, synthetic or expectation-based** JSON corpora. They are part of the reproducible test suite, not additional clinical-trial datasets.

| Corpus | Offline command | Interpretation |
|---|---|---|
| `cases.json` | `python -m evals.run --mode validate` | 50 labeled questions and expected plan fields; schema only |
| `identity_cases.json` | `python -m evals.identity` | 24 registered intervention identity labels |
| `grounding_cases.json` | `python -m evals.grounding` | 54 labels for invented-filter detection |
| `recall_cases.json` | `python -m evals.recall` | 74 labels for omitted-filter detection |

Live OpenAI evaluation is opt-in, may incur charges, and requires `OPENAI_API_KEY`:

```bash
python -m evals.run --mode live --limit 10 --output evals/reports/planner.json
python -m evals.run --mode live --category multi_filter --limit 10
python -m evals.run --mode guarded --limit 10 --output evals/reports/guarded.json
```

`live` reports structured response validity, intent agreement, annotated filter accuracy and **requested-filter recall**. Positively labeled filters form the recall denominator; null/false/unannotated filters do not. `guarded` measures whether the actual runtime validation (and at most one repair) accepts supported queries and rejects `unsupported` queries, without using the registry. It may consume two model calls for a rejected candidate. Inspect case-level failures instead of claiming general semantic accuracy from an aggregate score. Neither mode measures clinical terminology recall or correctness of source data.

`evals/reports/` is Git-ignored. Never publish reports containing private prompts or provider credentials.
