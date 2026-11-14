"""An invalid LLM plan gets at most one correction; retrieval remains fail-closed."""
import pytest
from app.agent.orchestrator import AnalysisService
from app.errors import QueryError, PlanningError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import SearchResult


class Planner:
    def __init__(self, initial, fixed=None):
        self.initial, self.fixed = initial, fixed
        self.calls = 0
        self.repairs = []

    async def plan(self, question):
        self.calls += 1
        return self.initial

    async def repair(self, question, prior_plan, issue):
        self.repairs.append((question, prior_plan, issue))
        if isinstance(self.fixed, Exception):
            raise self.fixed
        return self.fixed


class Registry:
    def __init__(self):
        self.calls = 0

    async def search(self, plan, *, max_studies, drug=None):
        self.calls += 1
        return SearchResult((), 0, True)


@pytest.mark.asyncio
async def test_one_repair_recovers_missing_country_without_unfiltered_registry_call():
    planner = Planner(
        QueryPlan(intent="phase_distribution", condition="melanoma"),
        QueryPlan(intent="phase_distribution", condition="melanoma", country="Canada"),
    )
    registry = Registry()
    result = await AnalysisService(planner, registry).analyze(
        AnalyzeRequest(query="Show melanoma trials in Canada by phase")
    )
    assert registry.calls == 1
    assert planner.calls == 1
    assert len(planner.repairs) == 1
    assert "country" in planner.repairs[0][2]
    assert result.meta.planner_attempts == 2
    assert result.meta.planner_repaired is True
    assert result.meta.filters["country"] == "Canada"
    assert any("repaired" in warning for warning in result.meta.warnings)


@pytest.mark.asyncio
async def test_invalid_repair_fails_closed_after_one_attempt():
    planner = Planner(QueryPlan(intent="phase_distribution"), QueryPlan(intent="phase_distribution"))
    registry = Registry()
    with pytest.raises(QueryError, match="omitted"):
        await AnalysisService(planner, registry).analyze(
            AnalyzeRequest(query="Show melanoma trials by phase")
        )
    assert len(planner.repairs) == 1
    assert registry.calls == 0


@pytest.mark.asyncio
async def test_unsupported_user_filter_does_not_trigger_repair():
    planner = Planner(QueryPlan(intent="phase_distribution"), QueryPlan(intent="phase_distribution"))
    registry = Registry()
    with pytest.raises(QueryError, match="cannot be represented"):
        await AnalysisService(planner, registry).analyze(
            AnalyzeRequest(query="Show trials not recruiting by phase")
        )
    assert planner.repairs == []
    assert registry.calls == 0


@pytest.mark.asyncio
async def test_valid_plan_never_spends_repair_call():
    planner = Planner(QueryPlan(intent="phase_distribution", condition="melanoma"))
    result = await AnalysisService(planner, Registry()).analyze(
        AnalyzeRequest(query="Show melanoma trials by phase")
    )
    assert result.meta.planner_attempts == 1
    assert not result.meta.planner_repaired
    assert planner.repairs == []


@pytest.mark.asyncio
async def test_unsupported_initial_plan_is_not_auto_overridden():
    planner = Planner(QueryPlan(intent="unsupported"), QueryPlan(intent="phase_distribution"))
    registry = Registry()
    with pytest.raises(QueryError, match="unsupported"):
        await AnalysisService(planner, registry).analyze(AnalyzeRequest(query="Can this medication cure cancer?"))
    assert registry.calls == 0
    assert planner.repairs == []


@pytest.mark.asyncio
async def test_provider_failure_during_repair_does_not_retrieve():
    planner = Planner(QueryPlan(intent="phase_distribution"), PlanningError("planner unavailable"))
    registry = Registry()
    with pytest.raises(PlanningError):
        await AnalysisService(planner, registry).analyze(
            AnalyzeRequest(query="Show melanoma trials by phase")
        )
    assert registry.calls == 0
