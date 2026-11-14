import pytest

from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import SearchResult


class FixedPlanner:
    def __init__(self, plan):
        self.plan_result = plan

    async def plan(self, query: str):
        return self.plan_result


class FixedTrials:
    def __init__(self, studies):
        self.records = studies
        self.calls = []

    async def search(self, plan, *, max_studies, drug=None):
        self.calls.append((plan, max_studies, drug))
        return SearchResult(tuple(self.records), len(self.records), True)


@pytest.mark.asyncio
async def test_explicit_filters_override_model_and_filter_records(studies):
    planner = FixedPlanner(QueryPlan(intent="geography", country="Germany"))
    registry = FixedTrials(studies)
    service = AnalysisService(planner, registry)
    response = await service.analyze(AnalyzeRequest(
        query="Which countries have trials?", country="Canada"
    ))
    assert response.meta.query_plan.country == "Canada"
    assert response.meta.records_fetched == 3
    assert response.meta.records_used == 1
    assert response.visualization.data[0]["country"] == "Canada"


@pytest.mark.asyncio
async def test_comparison_requires_two_drugs(studies):
    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="drug_comparison", drugs=["Drug A"])),
        FixedTrials(studies),
    )
    with pytest.raises(QueryError):
        await service.analyze(AnalyzeRequest(query="compare two drugs"))


@pytest.mark.asyncio
async def test_no_matching_data_is_explicit(studies):
    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="phase_distribution", country="Mars")),
        FixedTrials(studies),
    )
    result = await service.analyze(AnalyzeRequest(query="Show trials in Mars"))
    assert result.visualization.data == []
    assert any("No matching" in w for w in result.meta.warnings)


@pytest.mark.asyncio
async def test_complete_retrieval_can_have_truncated_network_display():
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    many = [
        normalize_study(raw_study(f"NCT{i:08d}", drugs=[f"Drug {i}"]))
        for i in range(1, 91)
    ]
    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="sponsor_drug_network")),
        FixedTrials(many),
    )
    result = await service.analyze(AnalyzeRequest(query="Show sponsor-drug network"))
    assert result.meta.complete is True
    assert result.meta.visualization_truncated is True
    assert result.meta.visualization_total_items == 90
    assert result.meta.visualization_items_returned == 75
    assert any("only 75 of 90" in text for text in result.meta.warnings)


def test_future_calendar_date_in_same_year_is_identified():
    from datetime import date
    from app.agent.orchestrator import is_future_study_start
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    record = raw_study("NCT00000012", year=2026)
    record["protocolSection"]["statusModule"]["startDateStruct"]["date"] = "2026-12-31"
    future = normalize_study(record)
    assert is_future_study_start(future, date(2026, 11, 14)) is True
    assert is_future_study_start(future, date(2027, 1, 1)) is False

    record["protocolSection"]["statusModule"]["startDateStruct"]["date"] = "2026"
    partial = normalize_study(record)
    assert is_future_study_start(partial, date(2026, 11, 14)) is False
