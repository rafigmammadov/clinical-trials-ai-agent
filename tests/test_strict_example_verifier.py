"""Strict-registry-matching examples must retain cohort-member provenance."""

import json

import pytest

from app.agent.orchestrator import AnalysisService
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.clinicaltrials import SearchResult
from app.services.normalizer import normalize_study
from scripts.verify_examples import verify_example
from tests.conftest import raw_study


class Planner:
    async def plan(self, _):
        return QueryPlan(intent="phase_distribution", drugs=["Keytruda"])


class Trials:
    async def search(self, *_args, **_kwargs):
        raw = raw_study("NCT00000042", drugs=[])
        raw["protocolSection"]["armsInterventionsModule"]["interventions"] = [
            {"type": "DRUG", "name": "Pembrolizumab", "otherNames": ["Keytruda"]},
        ]
        return SearchResult((normalize_study(raw),), 1, True)


@pytest.mark.asyncio
async def test_strict_generated_result_requires_intervention_evidence(tmp_path):
    service = AnalysisService(Planner(), Trials())
    result = await service.analyze(AnalyzeRequest(
        query="Show phases of Keytruda clinical trials", drug_match_mode="registered_name"))
    path = tmp_path / "phase_distribution.json"
    path.write_text(result.model_dump_json())
    assert "FULL CHART" in verify_example(path, "bar_chart")
    data = result.model_dump(mode="json")
    del data["visualization"]["data"][0]["citations"][0]["matched_drug_excerpt"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="membership evidence"):
        verify_example(path, "bar_chart")
