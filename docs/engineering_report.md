# Engineering report — reliability iteration

Date: 2026-11-14. The patch is intended for the previously published 46-commit baseline; GitHub could be inspected but not cloned directly from this execution environment. The owner must verify `git apply --check` and run the final gates on their actual checkout.

## Executive summary

The initial code separated LLM intent planning from deterministic registry-backed aggregation and had 60 passing offline tests. The review added explicit unsupported-query handling, stronger completeness and chart-support accounting, normalized record identity, deterministic graph labels, a 50-case planner benchmark, pagination/property tests, failure injection, evidence-scope disclosures and safer ZIP packaging.

## Initial versus updated state

| Dimension | Initial verified state | Updated offline state |
| --- | --- | --- |
| Unit/integration tests | 60 passing | 98 passing offline on Python 3.13 |
| Planner rejection | No explicit unsupported intent | Schema enum plus pre-retrieval 422 |
| Counting metadata | Retrieved, post-filter, retrieval completeness | Adds distinct visualized/not-visualized counts |
| Malformed records without totalCount | Could still report `complete=True` | Always reported incomplete |
| Histogram/scatter inputs | Could double-count duplicate NCT records when called directly | Builder deduplicates |
| Graph labels | Last-seen capitalization could win | Deterministic canonical label |
| Sparse field citations | Could fall back silently to NCT ID | Labels identity-only citation scope |
| Reproducible agent evaluation | No labeled benchmark | 50 cases with opt-in live scoring |
| Packaging | Recursive ZIP | Allowlisted source ZIP, credential check, content inspection |

## Evidence / tests

- Reproduced failures before fixing: `tests/test_release_correctness.py` and `tests/test_metamorphic.py`.
- Final offline run: **98 tests passed** on Python 3.13, with no warnings in this container. Automated runtime check took approximately 0.8 seconds; it excludes network I/O.
- Applying the unified patch to a fresh copy of the source passed `git apply --check` and the 98-test suite.
- A packaging rehearsal with five **synthetic mock** JSON fixtures passed the JSON verifier and produced a 60-file source archive that passed post-build inspection. Those mock examples are not authentic registry outputs and are not included in the user-facing patch.
- New/updated test files: `test_release_correctness`, `test_metamorphic`, `test_failure_injection`, `test_evals`, `test_archive`.
- Live GPT and live ClinicalTrials.gov calls were **not executed in this container**, because the environment could not reach the providers or use the owner's credential. Do not infer a live accuracy score from passing unit tests.
- Existing saved live examples passed on the owner's Mac before this patch. They need validation and, where response fields changed, regeneration after applying it.

## Synthetic performance spot check

A measured, local single-process Python 3.13 run over **2,000 synthetic study fixtures** produced approximately:

| Operation | Time | JSON bytes |
| --- | ---: | ---: |
| Annual trend | 2.32 ms | 15,084 |
| Phase distribution | 1.48 ms | 1,152 |
| Geographic distribution | 1.36 ms | 1,334 |
| Sponsor–drug network | 18.66 ms | 57,270 |
| Drug co-occurrence network | 9.17 ms | 172,961 |
| Enrollment histogram | 1.97 ms | 9,975 |
| Enrollment scatter | 11.89 ms | 936,102 |

These are **one-off synthetic aggregation measurements**, not server latency, registry fetch duration, memory benchmarks, production SLAs, or live clinical data. Network truncation caused some of the 2,000 sample records to be unrepresented; metadata now makes this visible.

## Remaining risks and priorities

1. Live model interpretation should be measured using `python -m evals.run --mode live`. Results can vary across model versions and prompt wording.
2. Registry terms are text matches, not canonical drug and disease concepts. The API's source records can change over time.
3. The response's chart `data` contains dynamic dict rows rather than strict discriminated unions. Schema-level renderability has independent tests, but a stricter schema could reduce frontend implementation ambiguity.
4. There is no public-service authentication or rate limiting; this is a locally evaluated service rather than a hardened public endpoint.
5. Dependencies are ranged rather than locked. An offline `pip-audit` could not be performed here.
6. The full release ZIP, real examples and external CI must be inspected on the owner's machine after applying the patch.

## Release commands

```bash
python -m pytest -q
python -m compileall -q app tests scripts evals
python -m evals.run --mode validate
python -m scripts.verify_examples
bash scripts/package_release.sh
python -m scripts.audit_archive --inspect dist/clinical-trials-ai-agent.zip
```

Never claim any remote push or official submission happened unless it actually did.

## Subsequent local reliability iteration (unreleased)

This iteration begins with a reconstructed, offline-tested v0.2 snapshot rather than a writable GitHub checkout. The pre-change test suite passed 98 tests. The post-change suite passed 121 offline tests and the 50-case evaluation corpus validated without making any LLM calls.

- Changed `app/schemas/api.py` to reject incompatible channel encodings, dangling graph references and inconsistent response accounting.
- Changed `app/visualizations/builder.py` to preserve both scatter-axis evidence fields within one NCT citation. This slightly changes the scatter citation shape; `docs/api.md` documents the migration.
- Changed `app/main.py` and `app/agent/planner.py` to reuse and close the OpenAI client and provide privacy-conscious request tracing.
- Changed `app/services/clinicaltrials.py` to honor HTTP-date `Retry-After` and retry HTTP 408 with bounded delays.
- Changed `evals/run.py` to report per-category live benchmark results and close its planner client reliably.
- Added targeted regression tests and updated the README, API contract, architecture and security notes.

Unverified in the working environment: live OpenAI model calls, live registry counts, dependency vulnerability scanning, hosted CI and current GitHub commit state. No remote changes or official hiring submission were performed.

- Changed `app/config.py` to reject insecure non-loopback registry URLs and invalid or unbounded request timeouts; `tests/test_settings_security.py` covers these cases.
