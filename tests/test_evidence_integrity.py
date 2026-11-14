"""Independent provenance assertions against normalized source fixtures."""
import pytest
from app.schemas.api import QueryPlan
from app.services.normalizer import normalize_study
from app.services.evidence import verify_chart_evidence
from app.visualizations.builder import build_chart
from tests.conftest import raw_study


def _study(i=1, drugs=("Drug A", "Drug B")):
    return normalize_study(raw_study(f"NCT{i:08d}", year=2024, drugs=list(drugs)))


@pytest.mark.parametrize("intent", [
    "time_trend", "phase_distribution", "intervention_distribution",
    "status_distribution", "sponsor_distribution", "geography",
    "sponsor_drug_network", "drug_cooccurrence_network",
    "enrollment_histogram", "enrollment_scatter",
])
def test_chart_evidence_matches_source_across_chart_families(intent):
    studies = [_study(1), _study(2)]
    chart = build_chart(QueryPlan(intent=intent), studies, citation_limit=10)
    verify_chart_evidence(chart.visualization, studies)


def test_bad_cited_nct_is_rejected():
    study = _study()
    chart = build_chart(QueryPlan(intent="time_trend"), [study], citation_limit=10)
    chart.visualization.data[0]["citations"][0]["nct_id"] = "NCT99999999"
    with pytest.raises(ValueError, match="unknown"):
        verify_chart_evidence(chart.visualization, [study])


def test_fabricated_start_date_excerpt_is_rejected():
    study = _study()
    chart = build_chart(QueryPlan(intent="time_trend"), [study], citation_limit=10)
    chart.visualization.data[0]["citations"][0]["excerpt"] = "2030-01-01"
    with pytest.raises(ValueError, match="not supported"):
        verify_chart_evidence(chart.visualization, [study])


def test_fabricated_second_network_endpoint_is_rejected():
    study = _study()
    chart = build_chart(QueryPlan(intent="sponsor_drug_network"), [study], citation_limit=10)
    edge = chart.visualization.data["edges"][0]
    edge["citations"][0]["related_excerpt"] = "Drug Not Registered"
    with pytest.raises(ValueError, match="not supported"):
        verify_chart_evidence(chart.visualization, [study])


def test_wrong_field_path_cannot_launder_a_real_excerpt():
    study = _study()
    chart = build_chart(QueryPlan(intent="time_trend"), [study], citation_limit=10)
    chart.visualization.data[0]["citations"][0]["field_path"] = "made.up.path"
    with pytest.raises(ValueError, match="not supported"):
        verify_chart_evidence(chart.visualization, [study])

@pytest.mark.asyncio
async def test_source_evidence_failure_prevents_returning_a_misleading_chart(monkeypatch):
    from app.agent.orchestrator import AnalysisService
    from app.errors import IntegrityError
    from app.schemas.api import AnalyzeRequest
    from app.services.clinicaltrials import SearchResult
    from app.visualizations.builder import build_chart as original_builder

    study = _study()
    class Planner:
        async def plan(self, query):
            return QueryPlan(intent="time_trend", condition="melanoma", start_year=2024)
    class Registry:
        async def search(self, *args, **kwargs):
            return SearchResult((study,), 1, True)

    def corrupted_chart(*args, **kwargs):
        result = original_builder(*args, **kwargs)
        result.visualization.data[0]["citations"][0]["excerpt"] = "NOT A SOURCE VALUE"
        return result

    monkeypatch.setattr("app.agent.orchestrator.build_chart", corrupted_chart)
    with pytest.raises(IntegrityError):
        await AnalysisService(Planner(), Registry()).analyze(AnalyzeRequest(
            query="Show melanoma trial starts since 2024", start_year=2024))
