# Grounding model-generated query restrictions

The LLM produces a typed `QueryPlan`, but type correctness does not establish that a filter was requested. A perfectly valid plan containing `country=Canada` can silently change a geography chart if the user only asked for a worldwide view. This module prevents a defined subset of these failures **before** the first registry request.

## Trust boundary

`AnalysisService` runs the following steps:

1. Ask the configured planner for a schema-constrained plan.
2. Reject unsupported intent. Reconcile any invented end year using the existing temporal policy.
3. Apply explicit, Pydantic-validated structured request overrides.
4. Call `validate_plan_grounding(plan, request)`.
5. Only if validation succeeds, call ClinicalTrials.gov, normalize studies, aggregate deterministically and produce citations.

The guard does not make LLM calls or inspect trial records. Its decisions are deterministic and independently unit-testable. A rejected plan produces the existing `422 invalid_analysis` error. The service does **not** silently drop the suspicious filter or substitute a different condition or drug.

## Evidence policy

| Inferred field | What authorizes it | How it fails |
| --- | --- | --- |
| `condition` | The exact phrase, ignoring case and punctuation separators | Unrequested or explicitly excluded condition is rejected |
| `drugs` | Every drug name is present as a token-delimited phrase | Any invented or explicitly excluded drug rejects the plan |
| `sponsor` | Sponsor name is present as a token-delimited phrase | Sponsor added to a general sponsor-distribution request is rejected |
| `country` | Country name or a small, explicit US/USA/UK abbreviation group; supported abbreviations are canonicalized to `United States` or `United Kingdom` before retrieval | Invented geography and simple exclusions are rejected |
| `start_year` | A standalone calendar-year token | Calculated or invented dates without an explicit year are rejected |
| `recruiting_only=true` | A positive recruiting/enrollment phrase without a recognized negation | Non-recruiting requests cannot silently become recruiting-only |
| `end_year` | Existing temporal reconciliation from v0.4.1 | Invented closing dates rejected or safely cleared for unbounded `since YYYY` |

**Structured overrides** such as `{"country":"Canada"}` are the caller's explicit instructions. They take precedence for the named field, even when the natural-language question does not mention that field. Recognized country abbreviations are normalized to the registry's expected full country names after overrides are applied. An override of `condition` does not authorize an independently invented `sponsor` or `country`.

When a user asks for a synonym that the planner expands into a different name, this policy may conservatively reject it. The correct next step is to supply an explicit structured value or update a reviewed terminology-mapping policy, not to silently infer clinical equivalence.

A conflict between an explicit start/end year and the model's other boundary is mapped to `422`, not leaked as a Pydantic internal exception. For an unbounded `since YYYY` request, a model-imagined end year is reconciled before merging the structured year override.

## Examples

Allowed:

```json
{"query":"Show recruiting asthma trials in Canada by phase"}
```

An LLM plan containing `condition=asthma`, `country=Canada`, and `recruiting_only=true` has visible evidence for each restriction.

Rejected:

```json
{"query":"Show clinical trial phase distributions"}
```

A plan containing `condition=melanoma` would narrow the analysis without authorization. The service returns HTTP 422 before fetching studies.

Explicit override:

```json
{"query":"Show phase distributions for my selected cohort", "condition":"Fabry disease"}
```

The structured `condition` is intentionally applied. The planner may not add another unrequested sponsor, country, or drug restriction.

## Verification

```bash
python -m pytest -q tests/test_plan_grounding.py
python -m evals.grounding
python -m evals.run --mode validate
```

`evals/grounding_cases.json` contains **54 hand-labeled synthetic model plans**, spanning 20 accepted cases, 26 rejected cases, and 8 structured-override cases. The evaluation verifies *guard decisions*, not the probability of GPT producing a correct plan. The separate 50-query planner benchmark has opt-in live-model evaluation.

## Known limitations and non-goals

- Lexical evidence is not evidence of **correct clinical meaning**. A substring can be an explicitly mentioned but overly broad disease term; a negated phrase outside the limited local patterns may be misinterpreted.
- v0.6.0 adds a separate conservative [requested-filter recall guard](plan_recall.md) for some omissions, but neither guard can prove complete semantic fidelity or correct intent selection.
- No RxNorm/MeSH/CT vocabulary or general-purpose entity linker is used. Acronyms and domain synonyms beyond a tiny country-abbreviation table can be rejected even when clinically equivalent.
- Relative dates such as “last five years” are not deterministically resolved. Supply `start_year` explicitly if a year is important.
- The question text is untrusted; a malicious instruction can mention a filter value and thereby pass the lexical evidence check. The typed plan, fixed upstream destination, and deterministic analytics remain separate trust boundaries.
- Country aliases are convenience labels, not confirmation of geography; actual study sites are verified from returned registry data.

These tradeoffs prioritize avoiding silent cohort contamination over accepting every paraphrase. The guard is defense-in-depth, not a clinical language understanding guarantee.
