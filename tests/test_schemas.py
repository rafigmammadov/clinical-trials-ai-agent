import pytest
from pydantic import ValidationError

from app.schemas.api import AnalyzeRequest, QueryPlan


def test_minimum_query():
    assert AnalyzeRequest(query="Show phase distribution").max_studies == 1000


@pytest.mark.parametrize("payload", [
    {"query": "tiny"[:3]},
    {"query": "trials in years", "start_year": 2025, "end_year": 2020},
    {"query": "compare trials", "max_studies": 90000},
    {"query": "compare trials", "drugs": [""]},
    {"query": "compare trials", "unexpected": "oops"},
])
def test_bad_requests_rejected(payload):
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate(payload)


def test_plan_rejects_invalid_years():
    with pytest.raises(ValidationError):
        QueryPlan(intent="time_trend", start_year=2026, end_year=2020)
