"""ClinicalTrials.gov API v2 adapter: bounded, deduplicated, retryable pagination."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

from app.errors import UpstreamError
from app.schemas.api import QueryPlan
from app.services.normalizer import Study, normalize_study


@dataclass(frozen=True, slots=True)
class SearchResult:
    studies: tuple[Study, ...]
    total_matches: int | None
    complete: bool
    warnings: tuple[str, ...] = ()


class ClinicalTrialsClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str) -> None:
        self._http = http
        self._base_url = base_url.rstrip("/")

    @staticmethod
    def build_params(plan: QueryPlan, drug: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"format": "json", "countTotal": "true"}
        if plan.condition:
            params["query.cond"] = plan.condition
        if drug:
            params["query.intr"] = drug
        if plan.sponsor:
            params["query.spons"] = plan.sponsor
        if plan.country:
            params["query.locn"] = plan.country
        if plan.recruiting_only:
            params["filter.overallStatus"] = "RECRUITING"
        if plan.start_year is not None or plan.end_year is not None:
            low = f"{plan.start_year}-01-01" if plan.start_year else "MIN"
            high = f"{plan.end_year}-12-31" if plan.end_year else "MAX"
            params["filter.advanced"] = f"AREA[StartDate]RANGE[{low},{high}]"
        return params

    @staticmethod
    def retry_delay(value: str | None, attempt: int, *, now: datetime | None = None) -> float:
        """Bounded retry delay for RFC 9110 delta-seconds and HTTP-date values."""
        fallback = min(0.5 * (2 ** attempt), 4.0)
        if not value:
            return fallback
        value = value.strip()
        if value.isdecimal():
            return min(float(value), 4.0)
        try:
            until = parsedate_to_datetime(value)
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            current = now or datetime.now(timezone.utc)
            return max(0.0, min((until - current).total_seconds(), 4.0))
        except (TypeError, ValueError, OverflowError):
            return fallback

    async def _request(self, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            try:
                resp = await self._http.get(f"{self._base_url}/studies", params=params)
                if resp.status_code in {408, 429, 500, 502, 503, 504} and attempt < 2:
                    await asyncio.sleep(self.retry_delay(resp.headers.get("Retry-After"), attempt))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or not isinstance(data.get("studies"), list):
                    raise UpstreamError("ClinicalTrials.gov returned an unexpected JSON structure")
                return data
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < 2:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue
                raise UpstreamError("ClinicalTrials.gov is temporarily unreachable") from exc
            except httpx.HTTPStatusError as exc:
                raise UpstreamError(
                    f"ClinicalTrials.gov returned HTTP {exc.response.status_code}"
                ) from exc
            except ValueError as exc:
                raise UpstreamError("ClinicalTrials.gov returned invalid JSON") from exc
        raise UpstreamError("ClinicalTrials.gov retries exhausted")

    async def search(
        self, plan: QueryPlan, *, max_studies: int, drug: str | None = None
    ) -> SearchResult:
        params = self.build_params(plan, drug)
        seen: dict[str, Study] = {}
        token: str | None = None
        total: int | None = None
        warnings: list[str] = []
        skipped_records = 0
        while len(seen) < max_studies:
            request_params = {**params, "pageSize": min(1000, max_studies - len(seen))}
            if token:
                request_params["pageToken"] = token
            body = await self._request(request_params)
            if total is None and isinstance(body.get("totalCount"), int):
                total = body["totalCount"]
            before = len(seen)
            for raw in body["studies"]:
                try:
                    record = normalize_study(raw)
                except (TypeError, AttributeError, ValueError, KeyError):
                    skipped_records += 1
                    warnings.append("Skipped one record with missing/invalid required fields")
                    continue
                seen.setdefault(record.nct_id, record)
                if len(seen) >= max_studies:
                    break
            next_token = body.get("nextPageToken")
            if not next_token:
                token = None
                break
            if not isinstance(next_token, str) or next_token == token:
                raise UpstreamError("Invalid or repeated page token from ClinicalTrials.gov")
            if len(seen) == before:
                raise UpstreamError("Pagination made no progress while retrieving studies")
            token = next_token
        # A malformed study is an omitted source record even when totalCount is
        # absent; successful pagination alone does not prove data completeness.
        complete = (token is None and skipped_records == 0
                    and (total is None or len(seen) >= total))
        if not complete:
            warnings.append(
                f"Only {len(seen)} of {total if total is not None else 'unknown'} "
                "matching studies were retrieved; aggregated values may be incomplete or biased"
            )
        return SearchResult(tuple(seen.values()), total, complete, tuple(dict.fromkeys(warnings)))
