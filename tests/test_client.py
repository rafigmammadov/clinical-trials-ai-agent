import httpx
import pytest

from app.errors import UpstreamError
from app.schemas.api import QueryPlan
from app.services.clinicaltrials import ClinicalTrialsClient
from tests.conftest import raw_study


@pytest.mark.asyncio
async def test_pagination_deduplicates_records():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if "pageToken" not in params:
            return httpx.Response(200, json={
                "totalCount": 3,
                "studies": [raw_study("NCT00000001"), raw_study("NCT00000002")],
                "nextPageToken": "page-2",
            })
        return httpx.Response(200, json={
            "studies": [raw_study("NCT00000002"), raw_study("NCT00000003")]
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test/api/v2").search(
            QueryPlan(intent="time_trend", condition="melanoma", start_year=2020), max_studies=10
        )
    assert len(result.studies) == 3
    assert result.complete is True
    assert result.total_matches == 3
    assert calls[0]["query.cond"] == "melanoma"
    assert "AREA[StartDate]RANGE[2020-01-01,MAX]" in calls[0]["filter.advanced"]
    assert calls[1]["pageToken"] == "page-2"


@pytest.mark.asyncio
async def test_incomplete_results_are_flagged():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "totalCount": 40, "studies": [raw_study("NCT00000001")], "nextPageToken": "next"
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=1
        )
    assert result.complete is False
    assert any("incomplete" in warning for warning in result.warnings)


@pytest.mark.asyncio
async def test_bad_data_yields_safe_error():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"unexpected": []})
    )) as http:
        with pytest.raises(UpstreamError):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="time_trend"), max_studies=10
            )


@pytest.mark.asyncio
async def test_status_filter_uses_registered_value():
    params = ClinicalTrialsClient.build_params(QueryPlan(
        intent="geography", recruiting_only=True, country="Canada"
    ))
    assert params["filter.overallStatus"] == "RECRUITING"
    assert params["query.locn"] == "Canada"
