# Registered intervention matching

ClinicalTrials.gov exposes an intervention-text search endpoint (`query.intr`) and each returned study's registered intervention definitions. A text-query match is not, by itself, proof of an exact named-drug cohort. This release adds an optional, deterministic verification stage without altering the legacy query behavior.

## Retrieval and membership are separate operations

1. The existing planner extracts a drug term from the user question, or the caller supplies `drugs` explicitly.
2. `ClinicalTrialsClient` calls the registry's `query.intr` search to retrieve *candidate* studies, using the normal page and record limits.
3. With `drug_match_mode=registered_name`, the application examines each candidate's `armsInterventionsModule.interventions` list.
4. It retains a study only when an intervention has `type=DRUG` and either its registered `name` or one of its registered `otherNames` matches the requested term after Unicode NFKC normalization, whitespace folding, and case-insensitive comparison.
5. All statistics are computed from the retained distinct NCT IDs. The request's chosen matching mode and per-drug matched-cohort counts are returned in `meta`.

The default is `registry_text`, which keeps existing results unchanged. The `registered_name` setting is **opt-in** and must be selected as a structured request property; the LLM cannot silently change it. It requires a named drug filter. No new inference is delegated to an LLM.

## HTTP request

```json
{
  "query": "Compare trial phases for pembrolizumab and nivolumab",
  "drugs": ["pembrolizumab", "nivolumab"],
  "drug_match_mode": "registered_name",
  "max_studies": 1500,
  "citation_limit": 10
}
```

The API response retains its existing `visualization` and `meta` root objects. New metadata keys:

| Field | Meaning |
| --- | --- |
| `meta.drug_match_mode` | `registry_text` (default) or `registered_name` |
| `meta.matched_drug_counts` | Number of post-filter studies in each verified requested-drug cohort; `null` when strict matching is not selected |
| `meta.filters.drug_match_mode` | The selected mode when a drug term was supplied |

For strict comparisons, each cited phase-contributing study also has `related_field_path` and `related_excerpt` pointing to its registered intervention name or alias. Other strict drug analyses retain their existing chart-dimension citation and add `matched_drug_field_path` and `matched_drug_excerpt`. Capped citation arrays are still explicitly labeled, and the count calculations are not based on citation length.

`meta.complete` continues to mean that the **upstream text-query candidates** were fully retrieved, not that all biologically relevant therapies worldwide were discovered. Two requested names can resolve to the same registered intervention in one record. In that case a study can legitimately appear in both cohorts. `matched_drug_counts` are not necessarily disjoint.

## Deliberate limits

- This is registered-record identity verification, **not** RxNorm/MeSH mapping, formulation equivalence, dose equivalence, drug class recognition, typo correction, or fuzzy matching.
- Only `DRUG` intervention types participate in strict mode; `BIOLOGICAL` and other intervention types are not silently reclassified.
- A registry search can fail to retrieve a study even when a synonym is recorded on that study. Local matching cannot restore missing candidates. A zero strict count is **not** proof that no relevant trial exists.
- Punctuation and dose annotations remain significant. `MK-3475` is not automatically equivalent to `MK3475`; `Drug Alpha` does not match `Drug Alpha 50mg` unless the full requested term is explicitly registered as an alias.
- Registration data can change over time. Aliases are asserted by registry submitters, not independently verified clinical truth.
- The upstream total match count may be larger than the verified cohort. It is the number of **candidate text matches**, not the number of strictly verified matches.

## Verification

```bash
python -m pytest tests/test_intervention_identity.py tests/test_identity_evaluation.py -q
python -m evals.identity
python -m pytest -q
```

`evals/identity_cases.json` contains 24 hand-labeled **synthetic** intervention records. The runner tests the matching policy offline; it neither calls OpenAI nor ClinicalTrials.gov and must not be presented as live search-recall or clinical-accuracy evidence. End-to-end verification with actual registry records remains a separate required task.

For a real strict comparison example using a configured local server:

```bash
python scripts/generate_examples.py --max-studies 1500 --strict-comparison
python -m scripts.verify_examples
```

The generator overwrites `examples/comparison.json` with actual live API output. Inspect its cohort counts, citations, retrieval completeness and warnings before committing it. Run it only with the user's consent for billable model calls.
