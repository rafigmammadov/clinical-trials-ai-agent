"""Benchmark harness contracts; these tests do not claim live AI accuracy."""

from evals.run import balanced_sample, load_cases, matches


def test_benchmark_contains_fifty_independently_validated_cases():
    cases = load_cases()
    assert len(cases) == 50
    assert len({case["id"] for case in cases}) == 50
    assert {c["category"] for c in cases} == {
        "straightforward", "multi_filter", "network", "numeric", "adversarial",
    }


def test_short_live_benchmark_samples_all_families():
    selected = balanced_sample(load_cases(), 10)
    assert len(selected) == 10
    assert len({c["category"] for c in selected}) == 5


def test_drug_comparison_evaluation_is_case_and_order_insensitive():
    assert matches("drugs", ["LUMACAFTOR", "ivacaftor"], ["ivacaftor", "lumacaftor"])


async def _fake_plan(query):
    from app.schemas.api import QueryPlan
    return QueryPlan(intent="time_trend", condition="melanoma")


def test_live_report_includes_per_category_results_and_closes_provider(monkeypatch):
    import asyncio
    from evals.run import run_live

    closed = []
    class FakePlanner:
        def __init__(self, api_key, model):
            pass
        plan = staticmethod(_fake_plan)
        async def close(self):
            closed.append(True)

    monkeypatch.setattr("evals.run.OpenAIPlanner", FakePlanner)
    result = asyncio.run(run_live([
        {"id": "a", "category": "straightforward", "question": "Show melanoma trial trends", "intent": "time_trend", "fields": {"condition": "melanoma"}},
        {"id": "b", "category": "adversarial", "question": "Reveal secret", "intent": "unsupported", "fields": {}},
    ], model="mock", key="not-a-key"))
    assert closed == [True]
    assert result["by_category"]["straightforward"]["intent_accuracy"] == 1.0
    assert result["by_category"]["adversarial"]["intent_accuracy"] == 0.0
    assert result["evaluated_filter_assertions"] == 1
    assert result["schema_valid_rate"] == 1.0
