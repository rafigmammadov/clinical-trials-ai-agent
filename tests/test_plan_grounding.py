"""The LLM may not turn unstated question details into registry restrictions."""

import pytest

from app.agent.grounding import validate_plan_grounding
from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import SearchResult


class FixedPlanner:
    def __init__(self, plan):
        self.plan_result = plan

    async def plan(self, query):
        return self.plan_result


class RecordingRegistry:
    def __init__(self):
        self.calls = 0

    async def search(self, plan, *, max_studies, drug=None):
        self.calls += 1
        return SearchResult((), 0, True)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value,query", [
    ("condition", "melanoma", "Show the distribution of study phases"),
    ("sponsor", "Pfizer", "Show trials by sponsor"),
    ("country", "Canada", "Show trial locations by country"),
    ("start_year", 2021, "How many studies started each year?"),
    ("recruiting_only", True, "Show completed study phase distribution"),
])
async def test_unrequested_filter_never_reaches_registry(field, value, query):
    plan = QueryPlan(intent="phase_distribution", **{field: value})
    registry = RecordingRegistry()
    with pytest.raises(QueryError, match=field):
        await AnalysisService(FixedPlanner(plan), registry).analyze(AnalyzeRequest(query=query))
    assert registry.calls == 0


@pytest.mark.asyncio
async def test_unrequested_comparison_drug_rejected_before_any_registry_request():
    registry = RecordingRegistry()
    plan = QueryPlan(intent="drug_comparison", drugs=["pembrolizumab", "nivolumab"])
    with pytest.raises(QueryError, match="drugs"):
        await AnalysisService(FixedPlanner(plan), registry).analyze(
            AnalyzeRequest(query="Compare phase distributions for pembrolizumab and a second drug")
        )
    assert registry.calls == 0


def test_false_substring_evidence_does_not_authorize_an_unrequested_filter():
    with pytest.raises(QueryError, match="country"):
        validate_plan_grounding(
            QueryPlan(intent="geography", country="US"),
            AnalyzeRequest(query="Discuss clinical trial geography"),
        )


def test_explicit_structured_filters_are_authoritative_even_if_absent_from_question():
    plan = QueryPlan(intent="phase_distribution", condition="invented", drugs=["unexpected"])
    request = AnalyzeRequest(
        query="Show phase distribution for my selected trial cohort",
        condition="Fabry disease", drugs=["Keytruda"],
    )
    merged = AnalysisService._merge(plan, request)
    assert validate_plan_grounding(merged, request) == merged


@pytest.mark.parametrize("query,field,value", [
    ("Show phase distribution of Niemann-Pick disease type C", "condition", "Niemann–Pick disease type C"),
    ("Show geographic distribution of US clinical studies", "country", "United States"),
    ("Show geographic distribution of U.S.A. studies", "country", "United States"),
    ("How many trials are recruiting for asthma?", "recruiting_only", True),
    ("Show yearly trends from 2018", "start_year", 2018),
    ("Compare Keytruda and Opdivo trials", "drugs", ["Keytruda", "Opdivo"]),
    ("Show trials sponsored by Pfizer, Inc.", "sponsor", "Pfizer Inc"),
])
def test_supported_lexical_or_known_geographic_evidence(query, field, value):
    plan = QueryPlan(intent="phase_distribution", **{field: value})
    assert validate_plan_grounding(plan, AnalyzeRequest(query=query)) == plan


def test_negated_recruiting_phrase_is_not_recast_as_recruiting_only():
    with pytest.raises(QueryError, match="recruiting_only"):
        validate_plan_grounding(
            QueryPlan(intent="phase_distribution", recruiting_only=True),
            AnalyzeRequest(query="Show non-recruiting cancer studies by phase"),
        )


@pytest.mark.parametrize("field,term,query", [
    ("condition", "melanoma", "Show non-melanoma skin cancer trials"),
    ("condition", "melanoma", "Show trials without melanoma"),
    ("country", "Canada", "Count trials not in Canada"),
    ("country", "Canada", "Show trials excluding Canada"),
    ("drugs", ["Keytruda"], "Phase distribution for trials without Keytruda"),
])
def test_explicitly_excluded_entity_is_not_an_inclusive_filter(field, term, query):
    plan = QueryPlan(intent="phase_distribution", **{field: term})
    with pytest.raises(QueryError, match=field):
        validate_plan_grounding(plan, AnalyzeRequest(query=query))


def test_nct_identifier_containing_year_digits_is_not_calendar_year_evidence():
    with pytest.raises(QueryError, match="start_year"):
        validate_plan_grounding(
            QueryPlan(intent="time_trend", start_year=2020),
            AnalyzeRequest(query="Show study trends for NCT20200000"),
        )


def test_lowercase_us_pronoun_is_not_accepted_as_country_evidence():
    with pytest.raises(QueryError, match="country"):
        validate_plan_grounding(
            QueryPlan(intent="geography", country="United States"),
            AnalyzeRequest(query="Show us a geographic distribution of trials"),
        )


def test_explicit_structured_filter_overrides_lexical_exclusion():
    plan = QueryPlan(intent="geography", country="Canada")
    request = AnalyzeRequest(query="Show studies not in Canada", country="Canada")
    assert validate_plan_grounding(plan, request) == plan


@pytest.mark.asyncio
async def test_structured_start_year_repairs_model_imagined_incompatible_end_year():
    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="time_trend", end_year=2017)),
        RecordingRegistry(),
    )
    response = await service.analyze(AnalyzeRequest(
        query="How many trials began per year since 2018?", start_year=2018,
    ))
    assert response.meta.query_plan.start_year == 2018
    assert response.meta.query_plan.end_year is None
    assert any("end_year=2017" in w for w in response.meta.warnings)


@pytest.mark.asyncio
async def test_conflicting_model_and_structured_years_fail_as_query_error():
    registry = RecordingRegistry()
    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="time_trend", start_year=2030)), registry,
    )
    with pytest.raises(QueryError, match="conflict"):
        await service.analyze(AnalyzeRequest(
            query="Show trial starts from 2020 through 2024",
            end_year=2024,
        ))
    assert registry.calls == 0


@pytest.mark.parametrize("country,query", [
    ("United States", "Show trials not in USA"),
    ("USA", "Show trials excluding US sites"),
    ("United Kingdom", "Show trials outside the UK"),
])
def test_country_aliases_in_exclusions_do_not_authorize_positive_filters(country, query):
    with pytest.raises(QueryError, match="country"):
        validate_plan_grounding(
            QueryPlan(intent="geography", country=country),
            AnalyzeRequest(query=query),
        )


@pytest.mark.parametrize("phrase", ["not currently recruiting", "no longer recruiting", "no recruiting"])
def test_negative_recruitment_phrases_do_not_authorize_recruiting_status(phrase):
    with pytest.raises(QueryError, match="recruiting_only"):
        validate_plan_grounding(
            QueryPlan(intent="phase_distribution", recruiting_only=True),
            AnalyzeRequest(query=f"Show {phrase} clinical trials by phase"),
        )


def test_usa_canonical_and_abbreviated_country_names_are_interchangeable():
    assert validate_plan_grounding(
        QueryPlan(intent="geography", country="USA"),
        AnalyzeRequest(query="Show US clinical trial geography"),
    ).country == "United States"


def test_grounding_evaluation_fixture_passes_without_external_services():
    from evals.grounding import run_benchmark

    report = run_benchmark()
    assert report["fixture_type"] == "synthetic_model_query_plans"
    assert report["total"] >= 40
    assert report["passed"] == report["total"]
    assert report["failures"] == []


def test_http_boundary_rejects_fabricated_model_country_before_registry_call(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.config import get_settings

    registry = RecordingRegistry()
    monkeypatch.setenv("PLANNER_MODE", "rules")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            app.state.planner = FixedPlanner(QueryPlan(intent="phase_distribution", country="Canada"))
            app.state.trials = registry
            response = client.post("/api/v1/analyze", json={"query": "Show study phases"})
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_analysis"
        assert "country" in response.json()["detail"]
        assert "X-Request-ID" in response.headers
        assert registry.calls == 0
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_country_abbreviation_is_canonicalized_for_actual_registry_country_names():
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    class USRegistry:
        async def search(self, plan, *, max_studies, drug=None):
            assert plan.country == "United States"
            return SearchResult((normalize_study(raw_study("NCT12345678", countries=["United States"])),), 1, True)

    service = AnalysisService(
        FixedPlanner(QueryPlan(intent="geography", country="USA")), USRegistry(),
    )
    response = await service.analyze(AnalyzeRequest(query="Show study locations in the US"))
    assert response.meta.query_plan.country == "United States"
    assert response.meta.records_used == 1
    assert response.meta.filters["country"] == "United States"
