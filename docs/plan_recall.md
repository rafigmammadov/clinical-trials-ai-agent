# Query-plan recall and unsupported exclusions

The LLM is responsible for interpreting a question, not deciding which explicitly
requested filters are optional. v0.5.0 rejects model-generated *extra* filters;
v0.6.0 additionally detects a narrow, high-confidence set of *omitted or changed*
constraints. Both checks run before the first ClinicalTrials.gov request.

## Pipeline and decisions

1. The planner produces a typed `QueryPlan`.
2. The temporal guard reconciles an ungrounded upper-year restriction.
3. Explicitly typed request fields replace the corresponding model fields.
4. `validate_plan_grounding` rejects unsupported extra restrictions.
5. `validate_plan_recall` checks whether recognizable constraints from the
   original question were retained. It also rejects explicit unsupported
   exclusions such as `not in Canada` or `non-recruiting`.
6. Only a valid plan reaches the registry client.

Omissions and unsupported exclusions produce the existing
`422 {"error":"invalid_analysis","detail":"..."}` error response. No
model-generated correction, automatic insertion of clinical terms, or second
LLM request occurs. This is deliberately fail-closed; the caller can restate
the question or supply a typed filter. Explicit request fields are authoritative
for their respective dimensions; e.g. `country="France"` overrides a question
mentioning Canada. An explicit `recruiting_only=false` is **not** interpreted
as "non-recruiting": it means no positive RECRUITING-only restriction.

## Recognized requirement types

| Dimension | High-confidence text evidence | What the guard checks |
| --- | --- | --- |
| Condition | `melanoma`; `Fabry disease`; `breast cancer`; named `... syndrome`; other limited terms | Same normalized condition |
| Drug | Explicit `drug X`; two named terms in a drug-comparison request (`X vs Y`) | Each identified drug remains in the plan |
| Sponsor | `sponsored by Pfizer` or `sponsor: Roche` | Exact normalized sponsor name |
| Country | `in Canada`; `US trials`; `in the UK`; bounded country-name list | Country name/recognized US or UK alias |
| Study status | `recruiting breast cancer trials`; `studies currently recruiting` | `recruiting_only=true` |
| Year | `since 2018`; `from 2018 to 2024`; `between 2018 and 2024`; `studies started in 2024` | Correct start/end bounds; no end year for open-ended `since` |

If a query explicitly names two conditions or compares two countries, the
current scalar `condition`/`country` field cannot express both. The request
is rejected, not silently narrowed to one entity. The negative constraints and relative or exclusive year expressions recognized
by the guard cannot be safely expressed by the current inclusive year/search
filters and are rejected rather than silently ignored.

## Evaluation: two distinct uses of the word recall

**Offline guard-detection recall** uses `python -m evals.recall`. Its
74 hand-labeled **synthetic model plans** contain omitted, incorrect,
complete, explicitly overridden and unrestricted cases. Its
`omission_detection_recall` is the fraction of labeled missing fields the
guard detects. It is **not** the percentage of real GPT requests understood
correctly and uses no registry records or external model.

**Live query-plan filter recall** uses the existing benchmark with new
metrics:

```bash
python -m evals.run --mode validate
python -m evals.run --mode live --category multi_filter --limit 10 \
  --output evals/reports/v060-multi-filter.json
```

The live `requested_filter_recall` counts correct **positive, labeled filter
assertions**, including absent ones that the model omitted. A model failure
counts as a missed assertion; unlabeled fields do not contribute. The report
retains `filter_accuracy`, which also includes negative/null/false assertions,
and breaks both measures down by query category. `null` means there were no
positive labeled assertions, **not** that recall is 100%.

These are metrics on a limited, hand-authored benchmark. Neither metric
establishes clinical ontology correctness, registry search recall, complete
prompt-injection protection or production reliability.

## Known limitations

- This is not a clinical entity recognition engine. Condition suffixes and a
  limited list of common conditions and countries are recognized; rarer
  conditions, proprietary drug brands, non-English text, arbitrary synonyms,
  and unrecognized geography can escape detection.
- Country names in organization names or user names may be ambiguous. The
  parser requires explicit country context, but cannot resolve all ambiguity.
- A drug-comparison parser handles simple single-token intervention names;
  multiword trade names and combination treatments need explicit `drugs`.
- Relative dates and the semantics of "active in 2024" versus "started in
  2024" are not inferred. Use structured year filters for exact requirements.
- The validator cannot determine if the chosen **intent** is semantically
  correct. Intent accuracy is evaluated separately.
- A candidate text-search result is not necessarily a verified drug identity:
  use `drug_match_mode="registered_name"` when registered intervention names
  and aliases are desired, with the known upstream candidate-recall limit.

Failing closed helps prevent silent corruption of counts. It can also reject
legitimate paraphrases, so it is a tradeoff rather than proof of semantic
completeness.
