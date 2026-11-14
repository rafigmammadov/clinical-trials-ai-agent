"""Exercise the offline example verification contract without live network calls."""

import json
from datetime import datetime, timezone

import pytest

from app.schemas.api import QueryPlan
from app.services.normalizer import normalize_study
from app.visualizations.builder import build_chart
from scripts.verify_examples import verify_example
from tests.conftest import raw_study


def _write_example(path, *, complete=True, truncated=False):
    record = normalize_study(raw_study("NCT00000001", year=2024))
    visualization = build_chart(
        QueryPlan(intent="time_trend", start_year=2024, end_year=2024),
        [record], citation_limit=3,
    ).visualization
    payload = {
        "visualization": visualization.model_dump(mode="json"),
        "meta": {
            "source": "ClinicalTrials.gov API v2",
            "source_url": "https://clinicaltrials.gov/data-api/api",
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "query_plan": {"intent": "time_trend", "start_year": 2024, "end_year": 2024},
            "filters": {"start_year": 2024},
            "records_fetched": 1,
            "records_used": 1,
            "total_matches": 1,
            "complete": complete,
            "warnings": [] if complete else ["Query was truncated"],
            "assumptions": [],
            "citation_limit_per_datum": 3,
            "cohort_matches": None,
            "visualization_truncated": truncated,
            "visualization_items_returned": 1,
            "visualization_total_items": 2 if truncated else 1,
        },
    }
    path.write_text(json.dumps(payload))
    return payload


def test_verifier_accepts_consistent_example(tmp_path):
    path = tmp_path / "time_trend.json"
    _write_example(path)
    assert "FULL CHART" in verify_example(path, "time_series")


def test_verifier_rejects_partial_data_by_default(tmp_path):
    path = tmp_path / "time_trend.json"
    _write_example(path, complete=False)
    with pytest.raises(ValueError, match="partial"):
        verify_example(path, "time_series")
    assert "FULL CHART" in verify_example(path, "time_series", allow_partial=True)


def test_verifier_rejects_inconsistent_chart_count(tmp_path):
    path = tmp_path / "time_trend.json"
    obj = _write_example(path)
    obj["visualization"]["data"][0]["trial_count"] = 99
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="count"):
        verify_example(path, "time_series")


def test_verifier_rejects_undisclosed_chart_truncation(tmp_path):
    path = tmp_path / "time_trend.json"
    obj = _write_example(path, truncated=True)
    obj["meta"]["visualization_total_items"] = 1
    path.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="truncation"):
        verify_example(path, "time_series")
