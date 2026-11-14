from app.schemas.api import QueryPlan
from app.visualizations.builder import build_chart


def test_trend_groups_by_year_with_exact_citations(studies):
    chart = build_chart(QueryPlan(intent="time_trend", start_year=2023, end_year=2025),
                        studies, citation_limit=3).visualization
    assert chart.type == "time_series"
    assert [(r["year"], r["trial_count"]) for r in chart.data] == [
        (2023, 1), (2024, 2), (2025, 0)
    ]
    assert chart.data[0]["citations"][0]["excerpt"] == "2023-03-01"


def test_multiphase_study_counted_once_per_phase(studies):
    chart = build_chart(QueryPlan(intent="phase_distribution"),
                        studies, citation_limit=3).visualization
    rows = {r["phase"]: r for r in chart.data}
    assert rows["Phase 1"]["trial_count"] == 1
    assert rows["Phase 2"]["trial_count"] == 2
    assert rows["Phase 3"]["trial_count"] == 1
    assert rows["Phase 2"]["citations"][0]["excerpt"] == "PHASE2"


def test_country_counts_distinct_nct_ids(studies):
    chart = build_chart(QueryPlan(intent="geography"), studies, citation_limit=3).visualization
    rows = {r["country"]: r["trial_count"] for r in chart.data}
    assert rows["Canada"] == 1
    assert rows["United States"] == 3


def test_grouped_comparison_includes_zeros(studies):
    chart = build_chart(
        QueryPlan(intent="drug_comparison", drugs=["Drug A", "Drug B"]), studies,
        citation_limit=3,
        cohorts={"Drug A": studies[:2], "Drug B": [studies[0], studies[2]]},
    ).visualization
    assert chart.type == "grouped_bar_chart"
    assert len(chart.data) == 14
    assert next(r for r in chart.data if r["drug"] == "Drug A" and r["phase"] == "Phase 3")["trial_count"] == 0


def test_sponsor_drug_graph_uses_study_edges(studies):
    chart = build_chart(QueryPlan(intent="sponsor_drug_network"), studies,
                        citation_limit=3).visualization
    assert chart.type == "network_graph"
    edge = next(e for e in chart.data["edges"]
                if e["source"] == "sponsor:acme research" and e["target"] == "drug:drug b")
    assert edge["weight"] == 2
    assert len(edge["citations"]) == 2


def test_drug_cooccurrence_graph(studies):
    chart = build_chart(QueryPlan(intent="drug_cooccurrence_network"), studies,
                        citation_limit=3).visualization
    weights = {(r["source"], r["target"]): r["weight"] for r in chart.data["edges"]}
    assert weights[("drug:drug a", "drug:drug b")] == 1
    assert weights[("drug:drug b", "drug:drug c")] == 1


def test_enrollment_histogram(studies):
    chart = build_chart(QueryPlan(intent="enrollment_histogram"), studies,
                        citation_limit=2).visualization
    assert chart.type == "histogram"
    assert sum(row["trial_count"] for row in chart.data) == 3


def test_scatter_has_study_references(studies):
    chart = build_chart(QueryPlan(intent="enrollment_scatter"), studies,
                        citation_limit=2).visualization
    assert chart.type == "scatter_plot"
    assert len(chart.data) == 3
    assert len(chart.data[0]["citations"]) == 2


def test_citation_limits_are_honored(studies):
    chart = build_chart(QueryPlan(intent="phase_distribution"), studies,
                        citation_limit=1).visualization
    two = next(x for x in chart.data if x["phase"] == "Phase 2")
    assert two["citation_count"] == 2
    assert two["citations_complete"] is False
    assert len(two["citations"]) == 1


def test_network_edge_citations_evidence_both_endpoints(studies):
    chart = build_chart(QueryPlan(intent="sponsor_drug_network"), studies,
                        citation_limit=3).visualization
    edge = next(e for e in chart.data["edges"]
                if e["source"] == "sponsor:acme research" and e["target"] == "drug:drug b")
    assert edge["citations"][0]["excerpt"] == "Acme Research"
    assert edge["citations"][0]["related_excerpt"] == "Drug B"


def test_network_top_75_edges_is_explicitly_flagged():
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    many = [
        normalize_study(raw_study(f"NCT{i:08d}", drugs=[f"Drug {i}"]))
        for i in range(1, 91)
    ]
    chart = build_chart(
        QueryPlan(intent="sponsor_drug_network"), many, citation_limit=3
    )
    assert chart.visualization_truncated is True
    assert chart.visualization_total_items == 90
    assert len(chart.visualization.data["edges"]) == 75
    assert any("top 75" in text for text in chart.assumptions)


def test_more_than_25_categories_is_flagged():
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    many = [
        normalize_study(raw_study(f"NCT{i:08d}", sponsor=f"Sponsor {i}"))
        for i in range(1, 31)
    ]
    result = build_chart(
        QueryPlan(intent="sponsor_distribution"), many, citation_limit=2
    )
    assert result.visualization_truncated is True
    assert result.visualization_total_items == 30
    assert len(result.visualization.data) == 25


def test_recruiting_geography_title_does_not_imply_recruiting_sites(studies):
    result = build_chart(
        QueryPlan(intent="geography", recruiting_only=True), studies, citation_limit=3
    )
    assert "listed study site" in result.visualization.title
    assert any("not necessarily an actively recruiting site" in a for a in result.assumptions)
