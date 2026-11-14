"""Metamorphic tests: different input presentations, identical factual results."""

from datetime import date
from itertools import permutations
from random import Random

import pytest

from app.agent.orchestrator import is_future_study_start
from app.schemas.api import QueryPlan
from app.services.normalizer import normalize_study
from app.visualizations.builder import build_chart
from tests.conftest import raw_study


def make_studies():
    return [
        normalize_study(raw_study(f"NCT{i:08d}", year=2020 + i % 4,
                  phases=["PHASE1", "PHASE2"] if i % 2 else ["PHASE3"],
                  drugs=["Drug A", "Drug B"] if i % 3 else ["Drug C"],
                  sponsor=f"Sponsor {i % 3}",
                  countries=["Canada", "United States"] if i % 2 else ["Germany"],
                  enrollment=i * 30))
        for i in range(1, 18)
    ]


@pytest.mark.parametrize("intent", [
    "time_trend", "phase_distribution", "intervention_distribution",
    "status_distribution", "sponsor_distribution", "geography",
    "sponsor_drug_network", "drug_cooccurrence_network",
    "enrollment_histogram", "enrollment_scatter",
])
def test_aggregation_invariant_under_permutation_and_identical_duplicates(intent):
    studies = make_studies()
    plan = QueryPlan(intent=intent, start_year=2020)
    original = build_chart(plan, studies, citation_limit=6)
    rng = Random(20261114)
    for _ in range(10):
        shuffled = list(studies)
        rng.shuffle(shuffled)
        duplicate_added = shuffled + shuffled[:3]
        actual = build_chart(plan, duplicate_added, citation_limit=6)
        assert actual.visualization.model_dump() == original.visualization.model_dump()
        assert actual.visualized_nct_ids == original.visualized_nct_ids


def test_case_variants_of_same_named_drug_have_stable_node_label():
    a = normalize_study(raw_study("NCT00000001", drugs=["Drug A"]))
    b = normalize_study(raw_study("NCT00000002", drugs=["drug a"]))
    plan = QueryPlan(intent="sponsor_drug_network")
    forward = build_chart(plan, [a, b], citation_limit=2).visualization.model_dump()
    backward = build_chart(plan, [b, a], citation_limit=2).visualization.model_dump()
    assert forward == backward


def test_future_month_can_be_excluded_without_day_precision():
    raw = raw_study("NCT00000005", year=2026)
    raw["protocolSection"]["statusModule"]["startDateStruct"]["date"] = "2026-12"
    record = normalize_study(raw)
    assert is_future_study_start(record, date(2026, 11, 14)) is True
    assert is_future_study_start(record, date(2026, 12, 1)) is False


def test_citation_sources_reference_contributing_nct_ids_only():
    studies = make_studies()
    plan = QueryPlan(intent="geography")
    chart = build_chart(plan, studies, citation_limit=40)
    by_nct = {study.nct_id: study for study in studies}
    for datum in chart.visualization.data:
        country = datum["country"]
        actual = {ref["nct_id"] for ref in datum["citations"]}
        expected = {s.nct_id for s in studies if country in s.countries}
        assert actual == expected
        for ref in datum["citations"]:
            assert country in by_nct[ref["nct_id"]].countries
            assert ref["excerpt"] == country
