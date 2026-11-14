"""Provider failure classification and pagination tests, all offline."""

import httpx
import pytest

from app.errors import UpstreamError
from app.schemas.api import QueryPlan
from app.services.clinicaltrials import ClinicalTrialsClient
from tests.conftest import raw_study


@pytest.mark.asyncio
async def test_503_retries_three_times_then_raises_safe_error(monkeypatch):
    attempts = 0

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.services.clinicaltrials.asyncio.sleep", no_sleep)

    def fail(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="INTERNAL CONFIDENTIAL TEXT")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
        with pytest.raises(UpstreamError) as exc:
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="phase_distribution"), max_studies=10
            )
    assert attempts == 3
    assert "503" in str(exc.value)
    assert "CONFIDENTIAL" not in str(exc.value)


@pytest.mark.asyncio
async def test_empty_json_array_is_not_treated_as_success():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json=[])
    )) as http:
        with pytest.raises(UpstreamError, match="unexpected JSON"):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="phase_distribution"), max_studies=10
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("page_size", [1, 2, 3, 10])
async def test_changing_page_boundaries_does_not_change_distinct_nct_ids(page_size):
    records = [raw_study(f"NCT{i:08d}") for i in range(1, 7)]

    def paginate(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("pageToken", "0"))
        chunk = records[offset: offset + page_size]
        new_offset = offset + len(chunk)
        body = {"totalCount": len(records), "studies": chunk}
        if new_offset < len(records):
            body["nextPageToken"] = str(new_offset)
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(paginate)) as http:
        response = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=100
        )
    assert response.complete
    assert len(response.studies) == 6
    assert {s.nct_id for s in response.studies} == {f"NCT{i:08d}" for i in range(1, 7)}
