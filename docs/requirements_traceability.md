# Requirements traceability

Reference: the original six-page clinical-trial query-to-visualization specification. This table records implemented behavior and test evidence, not a claim that every natural-language question succeeds.

| Requirement (page) | Source | Verification | Status/limitations |
| --- | --- | --- | --- |
| Required natural-language `query`, optional structured filters (1–2) | `app/schemas/api.py` | `tests/test_schemas.py`, `tests/test_hardening.py` | Implemented; filter precedence in orchestrator. |
| ClinicalTrials.gov authoritative source (1) | `app/services/clinicaltrials.py` | `tests/test_client.py`, `tests/test_failure_injection.py` | Implemented; live network verification required for a fresh release. |
| Interpret question and choose analysis (1, 3) | `app/agent/planner.py`, `app/agent/orchestrator.py` | `tests/test_service.py`, `evals/cases.json` | Structured plan; live semantic accuracy not established by offline tests. |
| Type/title/encoding/data visualization JSON (2–3) | `app/schemas/api.py`, `app/visualizations/builder.py` | `tests/test_charts.py`, `tests/test_example_verifier.py` | Implemented for six chart types and 11 supported analysis intents. |
| Frontend-usable metadata, units, sorting, assumptions (2–3) | `app/schemas/api.py`, `builder.py`, `README.md` | `tests/test_api.py`, `scripts/verify_examples.py` | Metadata includes retrieval/visualization completeness and support counts; front-end renderer itself not implemented. |
| Time series and grouped categorical comparisons (3, 6) | `builder._trend`, `builder._comparison` | `tests/test_charts.py`, `tests/test_release_correctness.py` | Implemented; missing/estimated dates and ambiguous intervention names disclosed. |
| Geography and drug/sponsor networks (3, 6) | `builder._distribution`, `builder._network` | `tests/test_charts.py`, `tests/test_metamorphic.py` | Implemented; site presence is not site-level recruitment. Network edge cap is explicit. |
| Histogram and scatter where meaningful (3) | `builder._histogram`, `builder._scatter` | `tests/test_charts.py`, `tests/test_metamorphic.py` | Implemented using enrollment; missing fields not charted. |
| Deep NCT citations with exact field excerpts (3–4 bonus) | `builder._source_field`, `builder._citations`, `builder._network` | `tests/test_charts.py`, `tests/test_release_correctness.py` | Implemented for present fields, with caps. Absent fields get explicit identity-only provenance, not fabricated text. |
| ZIP with source, README, 3–5 actual examples (4) | `scripts/package_release.sh`, `scripts/audit_archive.py` | `tests/test_archive.py`, `scripts/verify_examples.py` | Release script enforces at least 3 JSON examples; the owner's actual files must be verified in their environment. |
| Explain AI use and validation (5) | README, `docs/DECISIONS.md`, `docs/engineering_report.md` | Manual document review | Documented; authors must verify any personal contribution claims. |
| System design (5: 35%) | app boundaries and docs | Offline tests + architecture audit | Strong separation; large-scale service hardening remains outside assignment scope. |
| AI/agent design (5: 20%) | OpenAI Pydantic planner, unsupported cases, deterministic aggregation | Schema tests, 50-case benchmark corpus | Constrained design; no measured live semantic benchmark yet. |
| Code quality (5: 20%) | Typed schemas, error categories, mocked integration, deterministic tests | `python -m pytest -q` | Good offline evidence; dependencies not fully vulnerability-audited. |
| Query/visualization coverage (5: 15%) | 11 intents / six JSON visualization types | `tests/test_charts.py` | Good structural breadth; some clinical interpretations depend on text matching. |
| Input/output design (5: 10%) | strict request/response models and API docs | Pydantic API and examples | Implemented; `data` payload itself remains partially dynamic. |

## Indicative readiness (not an evaluator grade)

The architecture and verified offline coverage support an **engineering estimate** of approximately 78–88/100 on the five weighted categories, contingent on live integration, example accuracy, and reviewer expectations. This is not a predicted hiring outcome. The citation bonus is separately available, with limitations where per-datum references are capped or a source field is absent.
