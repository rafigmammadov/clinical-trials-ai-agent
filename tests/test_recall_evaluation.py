"""Measure omissions separately from full-field accuracy; offline-only tests."""

import asyncio

from app.schemas.api import QueryPlan
from evals.recall import run_benchmark
from evals.run import positive_requested_filters, run_live


def test_74_case_independently_labeled_omission_benchmark():
    report = run_benchmark()
    assert report["fixture_type"] == "synthetic_omitted_filter_plans"
    assert report["total"] == 74
    assert report["passed"] == 74
    assert report["failures"] == []
    assert report["omission_detection_recall"] == 1
    assert report["omission_detection_precision"] == 1
    assert report["by_category"]["unrestricted"]["passed"] == 13


def test_positive_filter_definition_ignores_unrequested_false_and_null():
    assert positive_requested_filters({
        "condition": "melanoma", "recruiting_only": False,
        "country": None, "drugs": [], "end_year": None,
        "start_year": 2019, "interpretation": "not a filter",
    }) == {"condition", "start_year"}


def test_live_plan_recall_score_tracks_omitted_expected_filters(monkeypatch):
    closed = []

    class FakePlanner:
        def __init__(self, api_key, model):
            pass

        async def plan(self, question):
            if question == "provider failure":
                raise RuntimeError("synthetic provider failure")
            return QueryPlan(intent="time_trend", condition="melanoma")

        async def close(self):
            closed.append(True)

    monkeypatch.setattr("evals.run.OpenAIPlanner", FakePlanner)
    cases = [
        {"id": "a", "category": "multi_filter", "question": "melanoma since 2020",
         "intent": "time_trend", "fields": {"condition": "melanoma", "start_year": 2020}},
        {"id": "b", "category": "multi_filter", "question": "provider failure",
         "intent": "time_trend", "fields": {"country": "Canada"}},
        {"id": "c", "category": "unrestricted", "question": "show all trial trends",
         "intent": "time_trend", "fields": {"recruiting_only": False, "end_year": None}},
    ]
    report = asyncio.run(run_live(cases, model="mock", key="not-a-real-key"))
    assert closed == [True]
    assert report["requested_filter_assertions"] == 3
    assert report["requested_filter_recall"] == 1 / 3
    assert report["by_category"]["multi_filter"]["requested_filter_recall"] == 1 / 3
    assert report["by_category"]["unrestricted"]["requested_filter_recall"] is None
    assert report["results"][0]["requested_filter_results"] == {
        "condition": True, "start_year": False,
    }
    assert report["results"][1]["requested_filter_results"] == {"country": False}
    assert report["results"][1]["error_type"] == "RuntimeError"
    assert "synthetic provider failure" not in str(report)


def test_case_insensitive_country_alias_comparison_for_labeled_recall():
    from evals.run import matches
    assert matches("country", "USA", "United States")
    assert matches("country", "UK", "United Kingdom")
    assert not matches("country", "United Kingdom", "United States")


def test_service_version_comes_from_single_module():
    from app.main import app
    from app.version import __version__
    assert app.version == __version__ == "0.6.0"
