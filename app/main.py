"""FastAPI presentation layer; endpoints contain no data or AI business logic."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from time import perf_counter
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent.orchestrator import AnalysisService
from app.agent.planner import OpenAIPlanner, RulesPlanner
from app.config import get_settings
from app.errors import PlanningError, QueryError, UpstreamError, IntegrityError
from app.schemas.api import AnalyzeRequest, AnalyzeResponse
from app.services.clinicaltrials import ClinicalTrialsClient
from app.version import __version__


logger = logging.getLogger("clinical_trials.http")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """One pooled connection client per application process."""
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.clinicaltrials_timeout_seconds) as http:
        app.state.trials = ClinicalTrialsClient(http, settings.clinicaltrials_api_url)
        # Construct one planner per process rather than one OpenAI HTTP pool
        # per request. Missing credentials do not prevent health checks.
        app.state.planner = (
            RulesPlanner() if settings.planner_mode == "rules"
            else OpenAIPlanner(settings.openai_api_key, settings.openai_model)
            if settings.openai_api_key else None
        )
        try:
            yield
        finally:
            if isinstance(app.state.planner, OpenAIPlanner):
                await app.state.planner.close()


app = FastAPI(
    title="Clinical Trials AI Agent",
    description=("Structured natural-language clinical trial analytics backed by "
                 "ClinicalTrials.gov, with deterministic data aggregation and citations."),
    version=__version__,
    lifespan=lifespan,
)


@app.middleware("http")
async def request_telemetry(request: Request, call_next):
    """Correlate requests without logging prompts, bodies, or credentials."""
    request_id = uuid4().hex
    started = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id, request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


@app.exception_handler(PlanningError)
async def planning_error_handler(_request: Request, _error: PlanningError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "planning_unavailable", "detail": str(_error)})


@app.exception_handler(QueryError)
async def query_error_handler(_request: Request, error: QueryError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "invalid_analysis", "detail": str(error)})


@app.exception_handler(UpstreamError)
async def upstream_error_handler(_request: Request, error: UpstreamError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": "registry_unavailable", "detail": str(error)})


@app.exception_handler(IntegrityError)
async def integrity_error_handler(_request: Request, _error: IntegrityError) -> JSONResponse:
    # An internal assertion failed. Do not reveal study values or server details.
    logger.error("visualization_evidence_integrity_failure")
    return JSONResponse(status_code=500, content={
        "error": "analysis_integrity_failure",
        "detail": "The visualization failed source-evidence validation",
    })


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
        "drug_match_modes": ["registry_text", "registered_name"],
        "frontend_required": False,
    }


@app.post("/api/v1/analyze", response_model=AnalyzeResponse, tags=["analysis"])
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    planner = request.app.state.planner
    if planner is None:
        raise PlanningError(
            "OPENAI_API_KEY is not configured; use PLANNER_MODE=rules for local smoke tests"
        )
    service = AnalysisService(planner=planner, trials=request.app.state.trials)
    return await service.analyze(payload)
