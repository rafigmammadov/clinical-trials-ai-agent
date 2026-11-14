"""FastAPI presentation layer; endpoints contain no data or AI business logic."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.orchestrator import AnalysisService
from app.agent.planner import OpenAIPlanner, RulesPlanner
from app.config import get_settings
from app.errors import PlanningError, QueryError, UpstreamError
from app.schemas.api import AnalyzeRequest, AnalyzeResponse
from app.services.clinicaltrials import ClinicalTrialsClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """One pooled connection client per application process."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.clinicaltrials_timeout_seconds) as http:
        app.state.trials = ClinicalTrialsClient(http, settings.clinicaltrials_api_url)
        yield


app = FastAPI(
    title="Clinical Trials AI Agent",
    description=("Structured natural-language clinical trial analytics backed by "
                 "ClinicalTrials.gov, with deterministic data aggregation and citations."),
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(PlanningError)
async def planning_error_handler(_request: Request, _error: PlanningError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "planning_unavailable", "detail": str(_error)})


@app.exception_handler(QueryError)
async def query_error_handler(_request: Request, error: QueryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "invalid_analysis", "detail": str(error)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_request: Request, error: UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "registry_unavailable", "detail": str(error)})


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "clinical-trials-agent", "version": app.version}


@app.get("/api/v1/capabilities", tags=["system"])
async def capabilities() -> dict[str, object]:
    return {
        "supported_intents": [
            "time_trend", "phase_distribution", "intervention_distribution",
            "status_distribution", "sponsor_distribution", "geography",
            "drug_comparison", "sponsor_drug_network", "drug_cooccurrence_network",
            "enrollment_histogram", "enrollment_scatter",
        ],
        "source": "ClinicalTrials.gov API v2",
        "frontend_required": False,
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse, tags=["analysis"])
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    settings = get_settings()
    planner = (RulesPlanner() if settings.planner_mode == "rules"
               else OpenAIPlanner(settings.openai_api_key, settings.openai_model))
    service = AnalysisService(planner=planner, trials=request.app.state.trials)
    return await service.analyze(payload)
