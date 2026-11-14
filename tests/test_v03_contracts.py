"""Regression tests for response contracts, traceability, and request lifecycles."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.api import QueryPlan, VisualizationSpec
from app.services.normalizer import normalize_study
from app.visualizations.builder import build_chart
from tests.conftest import raw_study


def test_scatter_has_one_citation_per_contributing_study_with_both_fields():
    study = normalize_study(raw_study("NCT00000001", year=2020, enrollment=123))
    result = build_chart(QueryPlan(intent="enrollment_scatter"), [study], citation_limit=1)
    row = result.visualization.data[0]
    assert row["citation_count"] == 1
    assert row["citations_complete"] is True
    assert len(row["citations"]) == 1
    ref = row["citations"][0]
    assert ref["field_path"] == "protocolSection.statusModule.startDateStruct.date"
    assert ref["related_field_path"] == "protocolSection.designModule.enrollmentInfo.count"
    assert ref["related_excerpt"] == "123"


def test_scatter_zero_citations_are_honestly_incomplete():
    study = normalize_study(raw_study("NCT00000002", enrollment=12))
    row = build_chart(QueryPlan(intent="enrollment_scatter"), [study], citation_limit=0).visualization.data[0]
    assert row["citation_count"] == 1
    assert row["citations"] == []
    assert row["citations_complete"] is False


def test_schema_rejects_network_edges_with_missing_nodes():
    with pytest.raises(ValidationError, match="unknown node"):
        VisualizationSpec.model_validate({
            "type": "network_graph", "title": "Invalid network",
            "encoding": {"nodes": {"id": "id"}, "edges": {"source": "source", "target": "target", "weight": "weight"}},
            "data": {"nodes": [{"id": "a", "label": "A", "kind": "drug"}],
                     "edges": [{"source": "a", "target": "not-present", "weight": 1}]},
        })


def test_schema_rejects_chart_row_missing_encoded_field():
    with pytest.raises(ValidationError, match="encoding"):
        VisualizationSpec.model_validate({
            "type": "bar_chart", "title": "Invalid data",
            "encoding": {"x": {"field": "phase", "type": "nominal"},
                         "y": {"field": "trial_count", "type": "quantitative"}},
            "data": [{"phase": "Phase 2", "wrong_count_field": 4}],
        })


def test_request_id_returned_on_health_and_validation_errors():
    with TestClient(app) as client:
        success = client.get("/health")
        bad = client.post("/api/v1/analyze", json={"query": "hi"})
    assert success.status_code == 200
    assert bad.status_code == 422
    assert success.headers["X-Request-ID"]
    assert bad.headers["X-Request-ID"]
    assert success.headers["X-Request-ID"] != bad.headers["X-Request-ID"]


def test_planner_is_app_scoped_and_reused(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("PLANNER_MODE", "rules")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            planner = client.app.state.planner
            client.get("/health")
            assert planner is client.app.state.planner
    finally:
        get_settings.cache_clear()


def test_retry_after_supports_http_date_and_caps_delay():
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from app.services.clinicaltrials import ClinicalTrialsClient

    now = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
    future = format_datetime(now + timedelta(seconds=20), usegmt=True)
    assert ClinicalTrialsClient.retry_delay(future, attempt=0, now=now) == 4.0
    near = format_datetime(now + timedelta(seconds=2), usegmt=True)
    assert ClinicalTrialsClient.retry_delay(near, attempt=0, now=now) == 2.0
    assert ClinicalTrialsClient.retry_delay("nonsense", attempt=1, now=now) == 1.0
    assert ClinicalTrialsClient.retry_delay("0", attempt=1, now=now) == 0.0


@pytest.mark.asyncio
async def test_client_retries_408_and_honors_retry_after(monkeypatch):
    import httpx
    from app.services.clinicaltrials import ClinicalTrialsClient

    observed_delays = []
    async def capture_sleep(delay):
        observed_delays.append(delay)
    monkeypatch.setattr("app.services.clinicaltrials.asyncio.sleep", capture_sleep)
    attempts = 0
    def response(_):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(408, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"studies": [raw_study("NCT00000001")], "totalCount": 1})
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as http:
        found = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=10
        )
    assert attempts == 2
    assert observed_delays == [2.0]
    assert found.complete and len(found.studies) == 1


def test_response_rejects_inconsistent_visualization_accounting():
    from datetime import datetime, timezone
    from app.schemas.api import AnalyzeResponse
    meta = {
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "query_plan": {"intent": "phase_distribution"},
        "filters": {}, "records_fetched": 3, "records_used": 3,
        "records_visualized": 2, "records_not_visualized": 0,
        "total_matches": 3, "complete": True, "warnings": [],
        "assumptions": [], "citation_limit_per_datum": 3,
        "visualization_truncated": False, "visualization_items_returned": 1,
    }
    with pytest.raises(ValidationError, match="records_not_visualized"):
        AnalyzeResponse.model_validate({
            "visualization": {"type": "bar_chart", "title": "Phase distribution",
                "encoding": {"x": {"field": "phase"}, "y": {"field": "trial_count"}},
                "data": [{"phase": "Phase 1", "trial_count": 2}]},
            "meta": meta,
        })


def test_response_rejects_mismatched_rendered_item_count():
    from datetime import datetime, timezone
    from app.schemas.api import AnalyzeResponse
    with pytest.raises(ValidationError, match="visualization_items_returned"):
        AnalyzeResponse.model_validate({
            "visualization": {"type": "bar_chart", "title": "Phases",
                "encoding": {"x": {"field": "phase"}, "y": {"field": "trial_count"}},
                "data": [{"phase": "Phase 2", "trial_count": 1}]},
            "meta": {"analyzed_at": datetime.now(timezone.utc).isoformat(),
                "query_plan": {"intent": "phase_distribution"},
                "filters": {}, "records_fetched": 1, "records_used": 1,
                "total_matches": 1, "complete": True, "warnings": [],
                "assumptions": [], "citation_limit_per_datum": 0,
                "visualization_items_returned": 2},
        })
