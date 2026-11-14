"""Official v2 pagination permits empty pages, but never unbounded loops."""
import httpx
import pytest

from app.errors import UpstreamError
from app.schemas.api import QueryPlan
from app.services.clinicaltrials import ClinicalTrialsClient
from tests.conftest import raw_study


@pytest.mark.asyncio
async def test_intermediate_empty_page_with_valid_next_token_is_allowed():
    pages = {
        None: {"studies": [raw_study("NCT00000001")], "totalCount": 2, "nextPageToken": "a"},
        "a": {"studies": [], "nextPageToken": "b"},
        "b": {"studies": [raw_study("NCT00000002")]},
    }
    calls = []
    def handler(request):
        token = request.url.params.get("pageToken")
        calls.append(token)
        return httpx.Response(200, json=pages[token])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="time_trend"), max_studies=10)
    assert calls == [None, "a", "b"]
    assert result.complete and len(result.studies) == 2


@pytest.mark.asyncio
async def test_pagination_cycle_is_detected_even_when_some_pages_have_records():
    def handler(request):
        token = request.url.params.get("pageToken")
        if token == "a":
            return httpx.Response(200, json={"studies": [raw_study("NCT00000002")], "nextPageToken": "b"})
        if token == "b":
            return httpx.Response(200, json={"studies": [raw_study("NCT00000003")], "nextPageToken": "a"})
        return httpx.Response(200, json={"studies": [raw_study("NCT00000001")], "nextPageToken": "a"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamError, match="page token"):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="time_trend"), max_studies=10)


@pytest.mark.asyncio
async def test_three_nonprogress_pages_are_bounded():
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        return httpx.Response(200, json={"studies": [], "nextPageToken": f"page{n}"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamError, match="no progress"):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="time_trend"), max_studies=10)
    assert n <= 4


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_total", [True, -2, "100"])
async def test_invalid_total_count_is_not_accepted(bad_total):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"studies": [], "totalCount": bad_total})
    )) as http:
        with pytest.raises(UpstreamError, match="totalCount"):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="time_trend"), max_studies=10)
