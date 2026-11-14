"""Registry-backed intervention identity: separate search from verified membership."""

import pytest
from pydantic import ValidationError

from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan
from app.services.intervention_matching import find_registered_drug_match
from app.services.normalizer import normalize_study
from app.services.clinicaltrials import SearchResult
from tests.conftest import raw_study


def record(nct: str, name: str, aliases=(), kind="DRUG"):
    raw = raw_study(nct, drugs=[])
    raw["protocolSection"]["armsInterventionsModule"]["interventions"] = [
        {"type": kind, "name": name, "otherNames": list(aliases)}
    ]
    return normalize_study(raw)


def test_normalizes_and_deduplicates_aliases():
    result = record("NCT00000100", "Pembrolizumab", [" KEYTRUDA ", "keytruda", "MK-3475", "", None])
    assert result.interventions[0].other_names == ("KEYTRUDA", "MK-3475")


def test_exact_name_is_case_and_whitespace_insensitive():
    matched = find_registered_drug_match(record("NCT00000101", "  Pembrolizumab  "), "PEMBROLIZUMAB")
    assert matched.field_path == "protocolSection.armsInterventionsModule.interventions[].name"
    assert matched.excerpt == "Pembrolizumab"


def test_registered_other_name_provides_source_evidence():
    matched = find_registered_drug_match(record("NCT00000102", "Pembrolizumab", ["Keytruda"]), "keytruda")
    assert matched.field_path == "protocolSection.armsInterventionsModule.interventions[].otherNames[]"
    assert matched.excerpt == "Keytruda"


def test_biological_or_non_drug_names_do_not_match():
    assert find_registered_drug_match(record("NCT00000103", "Keytruda", kind="BIOLOGICAL"), "Keytruda") is None


def test_substring_does_not_count_as_registered_identity():
    assert find_registered_drug_match(record("NCT00000104", "Drug Alpha 20 mg"), "Drug Alpha") is None


def test_invalid_drug_match_mode_rejected_at_request_boundary():
    with pytest.raises(ValidationError):
        AnalyzeRequest(query="What are drug trials?", drugs=["Keytruda"], drug_match_mode="fuzzy")


class PlannerStub:
    def __init__(self, plan):
        self.plan_result = plan

    async def plan(self, query):
        return self.plan_result


class RegistryStub:
    def __init__(self, records):
        self.records = tuple(records)
        self.calls = []

    async def search(self, plan, *, max_studies, drug=None):
        self.calls.append(drug)
        return SearchResult(self.records, len(self.records), True)


@pytest.mark.asyncio
async def test_single_drug_strict_excludes_text_search_false_positives():
    supported = record("NCT00000110", "Pembrolizumab", ["Keytruda"])
    false_positive = record("NCT00000111", "Other drug", ["Otherbrand"])
    service = AnalysisService(PlannerStub(QueryPlan(intent="phase_distribution", drugs=["Keytruda"])),
                              RegistryStub([supported, false_positive]))
    result = await service.analyze(AnalyzeRequest(
        query="Phase distribution for Keytruda", drug_match_mode="registered_name"))
    assert result.meta.records_fetched == 2
    assert result.meta.records_used == 1
    assert result.meta.drug_match_mode == "registered_name"
    assert result.meta.matched_drug_counts == {"Keytruda": 1}
    assert result.visualization.data[0]["trial_count"] == 1
    assert result.meta.complete is True
    assert any("registered" in a.lower() for a in result.meta.assumptions)


@pytest.mark.asyncio
async def test_legacy_registry_text_mode_preserves_current_behavior():
    supported = record("NCT00000110", "Pembrolizumab", ["Keytruda"])
    false_positive = record("NCT00000111", "Other drug")
    service = AnalysisService(PlannerStub(QueryPlan(intent="phase_distribution", drugs=["Keytruda"])),
                              RegistryStub([supported, false_positive]))
    result = await service.analyze(AnalyzeRequest(query="Phase distribution for Keytruda"))
    assert result.meta.records_used == 2
    assert result.meta.drug_match_mode == "registry_text"
    assert result.meta.matched_drug_counts is None


@pytest.mark.asyncio
async def test_strict_mode_with_no_drug_is_explicit_error():
    service = AnalysisService(PlannerStub(QueryPlan(intent="phase_distribution", condition="Asthma")),
                              RegistryStub([]))
    with pytest.raises(QueryError, match="requires"):
        await service.analyze(AnalyzeRequest(query="Phase distribution for asthma", drug_match_mode="registered_name"))


@pytest.mark.asyncio
async def test_comparison_evidence_proves_intervention_cohort_membership():
    both = record("NCT00000120", "Pembrolizumab", ["Keytruda", "MK-3475"])
    other = record("NCT00000121", "Nivolumab", ["Opdivo"])
    # Both cohorts share registry results but strict local matching separates memberships.
    service = AnalysisService(
        PlannerStub(QueryPlan(intent="drug_comparison", drugs=["Keytruda", "Opdivo"])),
        RegistryStub([both, other]))
    result = await service.analyze(AnalyzeRequest(
        query="Compare phases for Keytruda and Opdivo", drug_match_mode="registered_name"))
    rows = result.visualization.data
    positive = [row for row in rows if row["phase"] == "Phase 2" and row["trial_count"] == 1]
    assert len(positive) == 2
    assert result.meta.matched_drug_counts == {"Keytruda": 1, "Opdivo": 1}
    by_drug = {row["drug"]: row["citations"][0] for row in positive}
    assert by_drug["Keytruda"]["related_field_path"].endswith("otherNames[]")
    assert by_drug["Keytruda"]["related_excerpt"] == "Keytruda"
    assert by_drug["Opdivo"]["related_excerpt"] == "Opdivo"


@pytest.mark.asyncio
async def test_comparison_overlapping_aliases_are_not_claimed_disjoint():
    record_both = record("NCT00000130", "Pembrolizumab", ["Keytruda", "MK-3475"])
    service = AnalysisService(
        PlannerStub(QueryPlan(intent="drug_comparison", drugs=["Keytruda", "MK-3475"])),
        RegistryStub([record_both]))
    result = await service.analyze(AnalyzeRequest(
        query="Compare trials for Keytruda and MK-3475", drug_match_mode="registered_name"))
    assert result.meta.records_used == 1
    assert result.meta.matched_drug_counts == {"Keytruda": 1, "MK-3475": 1}
    assert sum(r["trial_count"] for r in result.visualization.data) == 2


@pytest.mark.asyncio
async def test_distribution_citations_include_separate_drug_membership_evidence():
    study = record("NCT00000140", "Pembrolizumab", ["Keytruda"])
    service = AnalysisService(
        PlannerStub(QueryPlan(intent="phase_distribution", drugs=["Keytruda"])),
        RegistryStub([study]))
    response = await service.analyze(AnalyzeRequest(
        query="Phase distribution for Keytruda", drug_match_mode="registered_name"))
    citation = response.visualization.data[0]["citations"][0]
    assert citation["field_path"] == "protocolSection.designModule.phases"
    assert citation["matched_drug_field_path"].endswith("otherNames[]")
    assert citation["matched_drug_excerpt"] == "Keytruda"


@pytest.mark.asyncio
async def test_strict_mode_no_match_has_explicit_recall_warning():
    service = AnalysisService(
        PlannerStub(QueryPlan(intent="phase_distribution", drugs=["Keytruda"])),
        RegistryStub([record("NCT00000141", "Nivolumab")]))
    response = await service.analyze(AnalyzeRequest(
        query="Phase distribution for Keytruda", drug_match_mode="registered_name"))
    assert response.meta.records_used == 0
    assert any("does not prove" in warning for warning in response.meta.warnings)


def test_response_metadata_rejects_invented_verified_counts():
    from datetime import datetime, timezone
    from app.schemas.api import ResponseMeta

    data = dict(
        analyzed_at=datetime.now(timezone.utc),
        query_plan=QueryPlan(intent="phase_distribution", drugs=["Keytruda"]),
        filters={"drugs": ["Keytruda"]},
        records_fetched=2, records_used=1,
        total_matches=2, complete=True, warnings=[], assumptions=[],
        citation_limit_per_datum=10,
        drug_match_mode="registered_name",
        matched_drug_counts={"Keytruda": 2},
    )
    with pytest.raises(ValidationError, match="cohort counts"):
        ResponseMeta(**data)
    data["matched_drug_counts"] = {"Keytruda": 1}
    assert ResponseMeta(**data).matched_drug_counts == {"Keytruda": 1}
    data["drug_match_mode"] = "registry_text"
    with pytest.raises(ValidationError, match="cannot claim verified"):
        ResponseMeta(**data)


def test_malformed_registry_alias_payload_is_ignored_without_fabricated_match():
    raw = raw_study("NCT00000150", drugs=[])
    raw["protocolSection"]["armsInterventionsModule"]["interventions"] = [
        {"type": "DRUG", "name": "Pembrolizumab", "otherNames": {"name": "Keytruda"}},
    ]
    study = normalize_study(raw)
    assert study.interventions[0].other_names == ()
    assert find_registered_drug_match(study, "Keytruda") is None


@pytest.mark.asyncio
async def test_registry_adapter_to_strict_aggregation_end_to_end():
    """HTTP fixture includes a text candidate that lacks the claimed drug name."""
    import httpx
    from app.services.clinicaltrials import ClinicalTrialsClient

    true_record = raw_study("NCT00000160", drugs=[])
    true_record["protocolSection"]["armsInterventionsModule"]["interventions"] = [
        {"name": "Pembrolizumab", "otherNames": ["Keytruda"], "type": "DRUG"},
    ]
    unrelated = raw_study("NCT00000161", drugs=["Drug Alpha"])
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={
            "totalCount": 2,
            "studies": [true_record, unrelated],
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        service = AnalysisService(
            PlannerStub(QueryPlan(intent="phase_distribution", drugs=["Keytruda"])),
            ClinicalTrialsClient(http, "https://registry.example.test/api/v2"),
        )
        result = await service.analyze(AnalyzeRequest(
            query="Count trial phases for Keytruda", drug_match_mode="registered_name"))
    assert seen[0]["query.intr"] == "Keytruda"
    assert result.meta.total_matches == 2
    assert result.meta.complete is True
    assert result.meta.matched_drug_counts == {"Keytruda": 1}
    assert result.meta.records_fetched == 2
    assert result.meta.records_used == 1
    assert result.visualization.data[0]["trial_count"] == 1
    assert result.visualization.data[0]["citations"][0]["matched_drug_excerpt"] == "Keytruda"
