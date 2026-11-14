"""Adversarial offline cases for input trust boundaries and registry resilience."""

import httpx
import pytest
from pydantic import ValidationError

from app.errors import UpstreamError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import ClinicalTrialsClient
from app.services.normalizer import normalize_study
from tests.conftest import raw_study


@pytest.mark.parametrize("query", ["     ", "   no  ", "\n\t\n"])
def test_whitespace_only_or_too_short_question_is_rejected(query):
    with pytest.raises(ValidationError):
        AnalyzeRequest(query=query)


@pytest.mark.parametrize("field", ["condition", "sponsor", "country"])
def test_whitespace_only_structured_filter_is_rejected(field):
    with pytest.raises(ValidationError):
        AnalyzeRequest(query="Show trials", **{field: "   "})


def test_request_and_llm_plan_trim_names():
    request = AnalyzeRequest(query="  Compare two drugs  ", drugs=["  Drug A ", " Drug B  "])
    plan = QueryPlan(intent="drug_comparison", drugs=["  Drug A ", " Drug B "])
    assert request.query == "Compare two drugs"
    assert request.drugs == ["Drug A", "Drug B"]
    assert plan.drugs == ["Drug A", "Drug B"]


@pytest.mark.parametrize("bad_date", ["2026-13-01", "2026-02-30", "2026-00", "2026-2-03", "abcd", "2026-02-01junk"])
def test_malformed_registry_date_is_not_counted(bad_date):
    study = raw_study("NCT00000042", year=2026)
    study["protocolSection"]["statusModule"]["startDateStruct"]["date"] = bad_date
    normalized = normalize_study(study)
    assert normalized.start_year is None
    assert normalized.start_date is None


@pytest.mark.parametrize("partial_date", ["2026", "2026-02", "2026-02-28"])
def test_valid_partial_and_full_registry_dates_are_accepted(partial_date):
    study = raw_study("NCT00000043", year=2026)
    study["protocolSection"]["statusModule"]["startDateStruct"]["date"] = partial_date
    normalized = normalize_study(study)
    assert normalized.start_year == 2026
    assert normalized.start_date == partial_date


@pytest.mark.asyncio
async def test_transient_429_is_retried_without_leaking_provider_body(monkeypatch):
    calls = 0

    async def no_sleep(_delay):
        pass

    monkeypatch.setattr("app.services.clinicaltrials.asyncio.sleep", no_sleep)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="TOP-SECRET-PROVIDER-DETAIL")
        return httpx.Response(200, json={"totalCount": 1, "studies": [raw_study("NCT00000001")]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=100
        )
    assert calls == 2
    assert result.complete is True
    assert len(result.studies) == 1


@pytest.mark.asyncio
async def test_nontransient_http_failure_maps_to_safe_provider_error():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="TOP-SECRET-PROVIDER-DETAIL")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamError) as exc:
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="phase_distribution"), max_studies=100
            )
    assert "403" in str(exc.value)
    assert "TOP-SECRET" not in str(exc.value)


@pytest.mark.asyncio
async def test_skipped_bad_registry_record_keeps_dataset_incomplete():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "totalCount": 2,
            "studies": [raw_study("NCT00000001"), {"protocolSection": {}}],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await ClinicalTrialsClient(http, "https://example.test").search(
            QueryPlan(intent="phase_distribution"), max_studies=100
        )
    assert len(result.studies) == 1
    assert result.total_matches == 2
    assert result.complete is False
    assert any("Skipped one record" in x for x in result.warnings)


@pytest.mark.asyncio
async def test_repeated_registry_page_token_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("pageToken") == "same":
            return httpx.Response(200, json={
                "totalCount": 5,
                "studies": [raw_study("NCT00000002")],
                "nextPageToken": "same",
            })
        return httpx.Response(200, json={
            "totalCount": 5,
            "studies": [raw_study("NCT00000001")],
            "nextPageToken": "same",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(UpstreamError, match="page token"):
            await ClinicalTrialsClient(http, "https://example.test").search(
                QueryPlan(intent="phase_distribution"), max_studies=100
            )
