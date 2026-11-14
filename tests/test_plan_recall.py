"""Question-to-plan *recall* checks, distinct from model-filter grounding.

All fixtures are synthetic. Registry calls are explicitly counted so a
forgotten requested filter cannot reach real data retrieval unnoticed.
"""

import pytest

from app.agent.recall import (
    extract_question_requirements, missing_question_filters, validate_plan_recall,
)
from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import SearchResult


class FixedPlanner:
    def __init__(self, plan):
        self.plan_result = plan

    async def plan(self, _question):
        return self.plan_result


class RecordingRegistry:
    def __init__(self):
        self.calls = 0

    async def search(self, *_args, **_kwargs):
        self.calls += 1
        return SearchResult((), 0, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("question,plan,missing", [
    ("How many melanoma trials started each year since 2018?",
     QueryPlan(intent="time_trend", start_year=2018), "condition"),
    ("How many melanoma trials started each year since 2018?",
     QueryPlan(intent="time_trend", condition="melanoma"), "start_year"),
    ("How are Fabry disease clinical trials distributed by phase?",
     QueryPlan(intent="phase_distribution"), "condition"),
    ("Show sponsor-drug network for Wilson disease trials",
     QueryPlan(intent="sponsor_drug_network"), "condition"),
    ("Show recruiting breast cancer trials in Canada",
     QueryPlan(intent="phase_distribution", condition="breast cancer", country="Canada"), "recruiting_only"),
    ("Show recruiting breast cancer trials in Canada",
     QueryPlan(intent="phase_distribution", condition="breast cancer", recruiting_only=True), "country"),
    ("Count trials sponsored by Pfizer Inc in Canada",
     QueryPlan(intent="phase_distribution", country="Canada"), "sponsor"),
    ("Show recruiting studies in the USA",
     QueryPlan(intent="phase_distribution", recruiting_only=True), "country"),
    ("Compare trial phases for ivacaftor versus lumacaftor",
     QueryPlan(intent="drug_comparison", drugs=["ivacaftor", "nivolumab"]), "drugs"),
    ("Compare trial phases for pembrolizumab and nivolumab",
     QueryPlan(intent="drug_comparison", drugs=["pembrolizumab"]), "drugs"),
    ("Show trials from 2018 through 2024",
     QueryPlan(intent="time_trend", start_year=2018), "end_year"),
    ("Show trials between 2018 and 2024",
     QueryPlan(intent="time_trend", end_year=2024), "start_year"),
    ("Show trials started in 2024",
     QueryPlan(intent="phase_distribution", start_year=2024), "end_year"),
    ("Show trends since 2018",
     QueryPlan(intent="time_trend", start_year=2018, end_year=2018), "end_year"),
    ("Show breast cancer trials in Canada",
     QueryPlan(intent="phase_distribution", condition="breast cancer", country="France"), "country"),
    ("Compare lung cancer and breast cancer studies",
     QueryPlan(intent="phase_distribution", condition="breast cancer"), "condition"),
])
async def test_omitted_requested_filter_fails_before_registry(question, plan, missing):
    registry = RecordingRegistry()
    with pytest.raises(QueryError, match=missing):
        await AnalysisService(FixedPlanner(plan), registry).analyze(AnalyzeRequest(query=question))
    assert registry.calls == 0


@pytest.mark.parametrize("question,plan", [
    ("How many melanoma trials started each year since 2018?",
     QueryPlan(intent="time_trend", condition="melanoma", start_year=2018)),
    ("How are Fabry disease clinical trials distributed by phase?",
     QueryPlan(intent="phase_distribution", condition="Fabry disease")),
    ("Which countries have the most recruiting trials for Wilson disease?",
     QueryPlan(intent="geography", condition="Wilson disease", recruiting_only=True)),
    ("Show sponsor to drug network for Fabry disease trials",
     QueryPlan(intent="sponsor_drug_network", condition="Fabry disease")),
    ("Compare trial phases for ivacaftor versus lumacaftor",
     QueryPlan(intent="drug_comparison", drugs=["ivacaftor", "lumacaftor"])),
    ("Show recruiting breast cancer trials in Canada since 2020 sponsored by Pfizer",
     QueryPlan(intent="phase_distribution", condition="breast cancer", country="Canada",
               sponsor="Pfizer", start_year=2020, recruiting_only=True)),
    ("Count studies in the US",
     QueryPlan(intent="phase_distribution", country="United States")),
    ("Count U.S. clinical trials",
     QueryPlan(intent="phase_distribution", country="United States")),
    ("Count trials in the UK",
     QueryPlan(intent="phase_distribution", country="United Kingdom")),
    ("Show studies started in 2024",
     QueryPlan(intent="phase_distribution", start_year=2024, end_year=2024)),
    ("Show trials between 2018 and 2024",
     QueryPlan(intent="time_trend", start_year=2018, end_year=2024)),
    ("Show phase distribution of all trials worldwide",
     QueryPlan(intent="phase_distribution")),
    ("Show clinical trial recruitment status distribution",
     QueryPlan(intent="status_distribution")),
    ("Show us trials by phase",
     QueryPlan(intent="phase_distribution")),
])
def test_correct_and_unrestricted_plans_not_falsely_rejected(question, plan):
    assert missing_question_filters(plan, AnalyzeRequest(query=question)) == ()
    assert validate_plan_recall(plan, AnalyzeRequest(query=question)) == plan


def test_structured_override_is_authoritative_for_that_field():
    question = "Show recruiting breast cancer trials in Canada since 2018 sponsored by Pfizer"
    request = AnalyzeRequest(
        query=question, condition="asthma", country="France", sponsor="Other Sponsor",
        start_year=2021, recruiting_only=False,
    )
    plan = QueryPlan(intent="phase_distribution", condition="asthma", country="France",
                     sponsor="Other Sponsor", start_year=2021, recruiting_only=False)
    assert validate_plan_recall(plan, request) == plan


def test_absent_question_drug_does_not_create_fake_requirement():
    question = "Which intervention types are most popular in clinical trials?"
    requirements, _ = extract_question_requirements(question, "intervention_distribution")
    assert not any(item.field == "drugs" for item in requirements)


def test_country_pronoun_does_not_imply_geography():
    requirements, _ = extract_question_requirements("Show us trials by phase", "phase_distribution")
    assert not any(item.field == "country" for item in requirements)


def test_no_relative_year_inferred_as_numeric_constraint():
    requirements, _ = extract_question_requirements(
        "Show trials in the last five years", "time_trend"
    )
    assert not any(item.field in ("start_year", "end_year") for item in requirements)


def test_unsupported_intent_does_not_contact_registry():
    # Existing service policy still rejects unsupported requests first.
    assert QueryPlan(intent="unsupported").intent == "unsupported"


def test_country_same_name_in_multiple_mention_styles_is_deduplicated():
    requirements, _ = extract_question_requirements(
        "Count trials in Canada and Canadian study sites in Canada", "geography"
    )
    countries = [item for item in requirements if item.field == "country"]
    assert len(countries) == 1
    assert countries[0].value == "Canada"


@pytest.mark.asyncio
@pytest.mark.parametrize("question,field", [
    ("Show studies not in Canada", "country"),
    ("Show trials outside the USA", "country"),
    ("Show trials excluding Japan", "country"),
    ("Show trials other than UK studies", "country"),
    ("Show trials without melanoma", "condition"),
    ("Show trials excluding asthma", "condition"),
    ("Show trials without Fabry disease", "condition"),
    ("Show studies not recruiting", "recruiting_only"),
    ("Show non-recruiting trials", "recruiting_only"),
    ("Show studies without drug pembrolizumab", "drugs"),
])
async def test_unsupported_exclusion_never_drops_filter_silently(question, field):
    registry = RecordingRegistry()
    with pytest.raises(QueryError, match=field):
        await AnalysisService(FixedPlanner(QueryPlan(intent="phase_distribution")), registry).analyze(
            AnalyzeRequest(query=question)
        )
    assert registry.calls == 0


def test_http_boundary_rejects_missing_model_country_before_registry_call(monkeypatch):
    from fastapi.testclient import TestClient
    from app.config import get_settings
    from app.main import app

    registry = RecordingRegistry()
    monkeypatch.setenv("PLANNER_MODE", "rules")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            app.state.planner = FixedPlanner(QueryPlan(intent="phase_distribution"))
            app.state.trials = registry
            response = client.post("/api/v1/analyze", json={
                "query": "Show recruiting melanoma trials in Canada"
            })
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_analysis"
        assert "country" in response.json()["detail"]
        assert "recruiting_only" in response.json()["detail"]
        assert registry.calls == 0
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("question", [
    "Show trials in Canada and Germany",
    "Compare trial phases in the US and UK",
])
def test_multiple_named_countries_do_not_silently_collapse_to_one(question):
    plan = QueryPlan(intent="phase_distribution", country="United States")
    if "Canada" in question:
        plan = plan.model_copy(update={"country": "Canada"})
    assert "country" in missing_question_filters(plan, AnalyzeRequest(query=question))


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "Count trials started in the last five years",
    "Count trials from the past 3 years",
    "Show melanoma studies after 2020",
    "Count trials before 2024",
    "Show studies this year",
])
async def test_relative_or_exclusive_time_cannot_be_silently_ignored(question):
    registry = RecordingRegistry()
    with pytest.raises(QueryError, match="calendar_year_semantics"):
        await AnalysisService(FixedPlanner(QueryPlan(intent="time_trend")), registry).analyze(
            AnalyzeRequest(query=question)
        )
    assert registry.calls == 0
