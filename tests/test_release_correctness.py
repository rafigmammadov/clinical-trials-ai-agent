"""Regression cases found during the v0.2 engineering audit."""

import httpx
import pytest

from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import ClinicalTrialsClient, SearchResult
from app.services.normalizer import normalize_study
from tests.conftest import raw_study


class StubPlanner:
    def __init__(self, plan: QueryPlan):
        self.result = plan

    async def plan(self, query: str) -> QueryPlan:
        return self.result


class StubRegistry:
    def __init__(self, studies):
        self.studies = tuple(studies)
        self.called = False

    async def search(self, *args, **kwargs):
        self.called = True
        return SearchResult(self.studies, len(self.studies), True)


@pytest.mark.asyncio
async def test_unsupported_intent_does_not_call_registry():
    registry = StubRegistry([])
    service = AnalysisService(StubPlanner(QueryPlan(intent="unsupported")), registry)
    with pytest.raises(QueryError, match="unsupported"):
        await service.analyze(AnalyzeRequest(query="Tell me the weather"))
    assert not registry.called


@pytest.mark.asyncio
async def test_trend_meta_distinguishes_filtered_from_visualized_records():
    with_date = normalize_study(raw_study("NCT00000001", year=2020))
    raw = raw_study("NCT00000002", year=2020)
    raw["protocolSection"]["statusModule"]["startDateStruct"] = {}
    missing_date = normalize_study(raw)
    service = AnalysisService(
        StubPlanner(QueryPlan(intent="time_trend", start_year=None)),
        StubRegistry([with_date, missing_date]),
    )
    result = await service.analyze(AnalyzeRequest(query="Show the annual trial counts"))
    assert result.meta.records_used == 2
    assert result.meta.records_visualized == 1
    assert result.meta.records_not_visualized == 1
    assert sum(r["trial_count"] for r in result.visualization.data) == 1


@pytest.mark.asyncio
async def test_skipped_malformed_registry_record_cannot_mark_complete_without_total():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "studies": [raw_study("NCT00000001"), {"protocolSection": {}}]
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=100
        )
    assert result.complete is False
    assert len(result.studies) == 1
    assert any("Skipped" in w for w in result.warnings)


def test_invalid_nct_id_does_not_pass_normalization():
    raw = raw_study("NCTTHIS_IS_FAKE")
    with pytest.raises(ValueError, match="NCT"):
        normalize_study(raw)


def test_comparison_does_not_silently_drop_unknown_phase_category():
    from app.visualizations.builder import build_chart

    raw = raw_study("NCT00000099", phases=["PHASE99"])
    study = normalize_study(raw)
    chart = build_chart(
        QueryPlan(intent="drug_comparison", drugs=["Drug A", "Drug B"]),
        [study], citation_limit=2,
        cohorts={"Drug A": [study], "Drug B": []},
    )
    matching = [r for r in chart.visualization.data if r["phase"] == "PHASE99"]
    assert len(matching) == 2
    assert {r["drug"]: r["trial_count"] for r in matching} == {"Drug A": 1, "Drug B": 0}


def test_absent_field_citation_is_explicitly_identity_only():
    from app.visualizations.builder import build_chart

    raw = raw_study("NCT00000098")
    raw["protocolSection"]["designModule"].pop("phases")
    study = normalize_study(raw)
    chart = build_chart(QueryPlan(intent="phase_distribution"), [study], citation_limit=2)
    row = next(r for r in chart.visualization.data if r["phase"] == "Not Reported")
    assert row["citations"][0]["evidence_scope"] == "record_identity_only"


@pytest.mark.parametrize("payload", [
    {"intent": "time_trend", "condition": "x" * 201},
    {"intent": "time_trend", "sponsor": "s" * 201},
    {"intent": "time_trend", "country": "c" * 101},
    {"intent": "time_trend", "drugs": ["d" * 201]},
    {"intent": "time_trend", "interpretation": "i" * 501},
])
def test_model_plan_fields_are_bounded_even_without_explicit_request_filters(payload):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        QueryPlan.model_validate(payload)


@pytest.mark.asyncio
async def test_histogram_discloses_studies_without_enrollment():
    good = normalize_study(raw_study("NCT00000031", enrollment=300))
    raw = raw_study("NCT00000032")
    raw["protocolSection"]["designModule"].pop("enrollmentInfo")
    missing = normalize_study(raw)
    service = AnalysisService(
        StubPlanner(QueryPlan(intent="enrollment_histogram")), StubRegistry([good, missing])
    )
    response = await service.analyze(AnalyzeRequest(query="Show an enrollment histogram"))
    assert response.meta.records_fetched == 2
    assert response.meta.records_used == 2
    assert response.meta.records_visualized == 1
    assert response.meta.records_not_visualized == 1
