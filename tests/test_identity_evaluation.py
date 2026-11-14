"""Verify the independent, hand-labeled identity benchmark contract."""

import json

from evals.identity import evaluate_cases


def test_registered_identity_fixture_suite_matches_annotations():
    result = evaluate_cases()
    assert result["total"] == 24
    assert result["passed"] == 24
    assert result["failed_ids"] == []
    assert result["fixture_type"] == "synthetic_registered_interventions"


def test_benchmark_rejects_duplicate_case_ids(tmp_path):
    cases = [{"id": "duplicate", "term": "A", "interventions": [],
              "expected_field": None, "expected_excerpt": None}] * 2
    path = tmp_path / "identity_cases.json"
    path.write_text(json.dumps(cases))
    try:
        evaluate_cases(path)
        assert False, "Expected duplicate case detection"
    except ValueError as exc:
        assert "Duplicate identity case" in str(exc)
