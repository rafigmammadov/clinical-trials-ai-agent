"""Deterministic render-ready chart builders with study-level provenance."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from math import ceil
from typing import Any, Iterable

from app.schemas.api import QueryPlan, VisualizationSpec
from app.services.normalizer import Study


PHASE_LABELS = {
    "EARLY_PHASE1": "Early Phase 1",
    "PHASE1": "Phase 1",
    "PHASE2": "Phase 2",
    "PHASE3": "Phase 3",
    "PHASE4": "Phase 4",
    "NA": "Not Applicable",
}
PHASE_ORDER = ["Early Phase 1", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Not Applicable", "Not Reported"]


@dataclass(frozen=True, slots=True)
class ChartResult:
    visualization: VisualizationSpec
    assumptions: tuple[str, ...] = ()
    visualization_truncated: bool = False
    visualization_total_items: int | None = None
    visualized_nct_ids: frozenset[str] = frozenset()


def _source_field(kind: str, study: Study, value: str | int | None) -> tuple[str, str]:
    """Return the exact source field and its literal value, never invented excerpts."""
    fields = {
        "year": ("protocolSection.statusModule.startDateStruct.date", study.start_date),
        "phase": ("protocolSection.designModule.phases", next((p for p in study.phases if PHASE_LABELS.get(p, p) == value), None)),
        "sponsor": ("protocolSection.sponsorCollaboratorsModule.leadSponsor.name", study.sponsor),
        "country": ("protocolSection.contactsLocationsModule.locations[].country", value),
        "drug": ("protocolSection.armsInterventionsModule.interventions[].name", next((p for p in study.drugs if p.casefold() == str(value).casefold()), None)),
        "intervention": ("protocolSection.armsInterventionsModule.interventions[].type", value if value in study.intervention_types else None),
        "status": ("protocolSection.statusModule.overallStatus", study.status),
        "enrollment": ("protocolSection.designModule.enrollmentInfo.count", study.enrollment),
    }
    path, excerpt = fields.get(kind, ("protocolSection.identificationModule.nctId", study.nct_id))
    if excerpt is None:
        return "protocolSection.identificationModule.nctId", study.nct_id
    return path, str(excerpt)


def _citations(
    studies: Iterable[Study], *, field_kind: str, value: Any, limit: int
) -> dict[str, Any]:
    unique = {study.nct_id: study for study in studies}
    ordered = [unique[k] for k in sorted(unique)]
    refs = []
    for study in ordered[:limit]:
        field_path, excerpt = _source_field(field_kind, study, value)
        reference = {
            "nct_id": study.nct_id,
            "url": f"https://clinicaltrials.gov/study/{study.nct_id}",
            "field_path": field_path,
            "excerpt": excerpt,
        }
        if field_path == "protocolSection.identificationModule.nctId" and field_kind != "nct":
            # A record ID is provenance, not evidence that an absent field
            # had a particular value. Keep that distinction machine-readable.
            reference["evidence_scope"] = "record_identity_only"
        refs.append(reference)
    return {
        "citation_count": len(ordered),
        "citations_complete": len(ordered) <= limit,
        "citations": refs,
    }


def _chart(chart_type: str, title: str, encoding: dict[str, dict[str, Any]], data: Any) -> VisualizationSpec:
    return VisualizationSpec(type=chart_type, title=title, encoding=encoding, data=data)


def _standard_encoding(x_field: str, x_title: str, y_field: str = "trial_count", y_title: str = "Distinct studies") -> dict[str, dict[str, Any]]:
    return {
        "x": {"field": x_field, "type": "nominal", "title": x_title},
        "y": {"field": y_field, "type": "quantitative", "title": y_title, "aggregate": "none"},
    }


def _group_by(studies: Iterable[Study], labels: Any) -> dict[str, list[Study]]:
    buckets: dict[str, dict[str, Study]] = defaultdict(dict)
    for study in studies:
        for label in set(labels(study)):
            buckets[str(label)][study.nct_id] = study
    return {key: list(value.values()) for key, value in buckets.items()}


def _phase_labels(study: Study) -> list[str]:
    return [PHASE_LABELS.get(x, x) for x in study.phases] if study.phases else ["Not Reported"]


def _distribution(plan: QueryPlan, studies: list[Study], limit: int) -> ChartResult:
    cases = {
        "phase_distribution": ("phase", "Trial phase", _phase_labels, "phase"),
        "intervention_distribution": ("intervention_type", "Intervention type", lambda s: s.intervention_types or ("Not Reported",), "intervention"),
        "status_distribution": ("status", "Overall status", lambda s: [s.status or "Not Reported"], "status"),
        "sponsor_distribution": ("sponsor", "Lead sponsor", lambda s: [s.sponsor or "Not Reported"], "sponsor"),
        "geography": ("country", "Country", lambda s: s.countries, "country"),
    }
    field, title, selector, cite_kind = cases[plan.intent]
    buckets = _group_by(studies, selector)
    if plan.intent == "phase_distribution":
        keys = sorted(buckets, key=lambda x: (PHASE_ORDER.index(x) if x in PHASE_ORDER else 99, x))
    else:
        keys = sorted(buckets, key=lambda k: (-len(buckets[k]), k))
    top_keys = keys[:25]
    rows = [
        {field: key, "trial_count": len(buckets[key]), **_citations(buckets[key], field_kind=cite_kind, value=key, limit=limit)}
        for key in top_keys
    ]
    assumptions = ["Each NCT ID contributes once per category; multi-valued categories may count a trial more than once across categories."]
    if plan.intent == "geography":
        assumptions.append("Country means any listed study-site country, not necessarily an actively recruiting site.")
    if plan.intent == "sponsor_distribution":
        assumptions.append("Sponsor refers to the lead sponsor, not collaborators.")
    if any(label == "Not Reported" for label in buckets):
        assumptions.append(
            "An absent source field can be supported by a record-identity citation only, "
            "not an exact excerpt proving the field's absence."
        )
    if len(keys) > 25:
        assumptions.append("Only the top 25 categories by distinct study count are displayed.")
    chart_title = f"Clinical trials by {title.lower()}"
    if plan.intent == "geography":
        chart_title = (
            "Recruiting studies by country with a listed study site"
            if plan.recruiting_only
            else "Clinical trials by country with a listed study site"
        )
    return ChartResult(
        _chart("bar_chart", chart_title, _standard_encoding(field, title), rows),
        tuple(assumptions),
        visualization_truncated=len(keys) > len(top_keys),
        visualization_total_items=len(keys),
        visualized_nct_ids=frozenset(s.nct_id for key in top_keys for s in buckets[key]),
    )


def _trend(plan: QueryPlan, studies: list[Study], limit: int) -> ChartResult:
    buckets = _group_by((s for s in studies if s.start_year is not None), lambda s: [s.start_year])
    numeric_years = [int(y) for y in buckets]
    low = plan.start_year if plan.start_year is not None else (min(numeric_years) if numeric_years else None)
    high = plan.end_year if plan.end_year is not None else (datetime.now(timezone.utc).year if low is not None else (max(numeric_years) if numeric_years else None))
    years = range(low, high + 1) if low is not None and high is not None and low <= high else ()
    data = [
        {"year": year, "trial_count": len(buckets.get(str(year), [])),
         **_citations(buckets.get(str(year), []), field_kind="year", value=year, limit=limit)}
        for year in years
    ]
    encoding = _standard_encoding("year", "Study start year")
    encoding["x"].update({"type": "quantitative", "unit": "year"})
    return ChartResult(
        _chart("time_series", "Clinical trials started by year", encoding, data),
        ("Year is derived from startDateStruct.date; missing start dates are excluded. A start date may be estimated.",),
        visualized_nct_ids=frozenset(s.nct_id for year in years for s in buckets.get(str(year), [])),
    )


def _comparison(
    cohorts: dict[str, list[Study]], limit: int
) -> ChartResult:
    rows = []
    bucket_sets = {drug: _group_by(studies, _phase_labels) for drug, studies in cohorts.items()}
    extra_phases = sorted({phase for buckets in bucket_sets.values()
                           for phase in buckets if phase not in PHASE_ORDER})
    all_phases = [*PHASE_ORDER, *extra_phases]
    for drug, buckets in bucket_sets.items():
        for phase in all_phases:
            support = buckets.get(phase, [])
            rows.append({
                "drug": drug, "phase": phase, "trial_count": len(support),
                **_citations(support, field_kind="phase", value=phase, limit=limit),
            })
    encoding = _standard_encoding("phase", "Phase")
    encoding["color"] = {"field": "drug", "type": "nominal", "title": "Drug cohort"}
    return ChartResult(
        _chart("grouped_bar_chart", "Trial phase comparison by drug", encoding, rows),
        ("A trial mentioning both drugs can belong to both cohorts; totals are not disjoint.",
         "Registry intervention searches are full-text matches, not verified drug ontology mappings.",
         "Unrecognized phase labels are preserved rather than silently dropped."),
        visualized_nct_ids=frozenset(
            s.nct_id for group in cohorts.values() for s in group
        ),
    )


def _network(plan: QueryPlan, studies: list[Study], limit: int) -> ChartResult:
    edge_studies: dict[tuple[str, str], dict[str, Study]] = defaultdict(dict)
    node_meta: dict[str, dict[str, str]] = {}

    def register(node_id: str, label: str, kind: str, study: Study) -> None:
        # Labels must not change with API record order/capitalization variants.
        previous = node_meta.get(node_id)
        if previous is not None:
            label = min(label, previous["label"], key=lambda text: (text.casefold(), text))
        node_meta[node_id] = {"id": node_id, "label": label, "kind": kind}

    for study in studies:
        canonical_drugs = {name.strip().casefold(): name.strip() for name in study.drugs if name.strip()}
        drug_names = [canonical_drugs[k] for k in sorted(canonical_drugs)]
        if plan.intent == "sponsor_drug_network":
            if not study.sponsor:
                continue
            sponsor_id = f"sponsor:{study.sponsor.casefold()}"
            register(sponsor_id, study.sponsor, "sponsor", study)
            for drug in drug_names:
                drug_id = f"drug:{drug.casefold()}"
                register(drug_id, drug, "drug", study)
                edge_studies[(sponsor_id, drug_id)][study.nct_id] = study
        else:
            for left, right in combinations(drug_names, 2):
                left_id, right_id = f"drug:{left.casefold()}", f"drug:{right.casefold()}"
                register(left_id, left, "drug", study)
                register(right_id, right, "drug", study)
                edge_studies[(left_id, right_id)][study.nct_id] = study

    # Keep a bounded, deterministic graph for renderers.
    selected_edges = sorted(edge_studies, key=lambda e: (-len(edge_studies[e]), e))[:75]
    visible_support: dict[str, dict[str, Study]] = defaultdict(dict)
    for source, target in selected_edges:
        for node in (source, target):
            visible_support[node].update(edge_studies[(source, target)])
    nodes = [
        {**node_meta[n], **_citations(
            visible_support[n].values(),
            field_kind="sponsor" if n.startswith("sponsor:") else "drug",
            value=node_meta[n]["label"], limit=limit,
        )}
        for n in sorted(visible_support)
    ]
    edges = []
    for source, target in selected_edges:
        support = edge_studies[(source, target)]
        evidence = _citations(
            support.values(),
            field_kind="sponsor" if source.startswith("sponsor:") else "drug",
            value=node_meta[source]["label"], limit=limit,
        )
        # Edge provenance includes TWO exact observed source-field values per study.
        # A sponsor name alone or a single drug name cannot establish a relationship.
        for ref in evidence["citations"]:
            study = support[ref["nct_id"]]
            second_path, second_excerpt = _source_field("drug", study, node_meta[target]["label"])
            ref["related_field_path"] = second_path
            ref["related_excerpt"] = second_excerpt
        edges.append({"source": source, "target": target, "weight": len(support), **evidence})
    assumptions = ["Edges are weighted by distinct NCT IDs; duplicates within the same study do not inflate weight."]
    if len(edge_studies) > 75:
        assumptions.append("Only the top 75 edges by study count are returned; other relationships are omitted.")
    if plan.intent == "drug_cooccurrence_network":
        assumptions.append("Co-occurrence means two drug-named interventions appear in one study, not confirmed combination therapy.")
    else:
        assumptions.append("Sponsor nodes represent the lead sponsor only; drug nodes use registered intervention names.")
    return ChartResult(
        _chart("network_graph", "Clinical trial relationship network", {
            "nodes": {"id": "id", "label": "label", "category": "kind"},
            "edges": {"source": "source", "target": "target", "weight": "weight"},
        }, {"nodes": nodes, "edges": edges}), tuple(assumptions),
        visualization_truncated=len(edge_studies) > len(selected_edges),
        visualization_total_items=len(edge_studies),
        visualized_nct_ids=frozenset(
            nct for edge in selected_edges for nct in edge_studies[edge]
        ),
    )


def _histogram(studies: list[Study], limit: int) -> ChartResult:
    valid = [s for s in studies if s.enrollment is not None]
    values = [s.enrollment for s in valid]
    rows: list[dict[str, Any]] = []
    if values:
        low, high = min(values), max(values)
        width = max(1, ceil((high - low + 1) / 10))
        bucket_count = (high - low) // width + 1
        for idx in range(bucket_count):
            start, end = low + idx * width, min(high, low + (idx + 1) * width - 1)
            support = [s for s in valid if start <= s.enrollment <= end]
            rows.append({
                "bin_start": start, "bin_end": end, "trial_count": len(support),
                **_citations(support, field_kind="enrollment", value=start, limit=limit),
            })
    return ChartResult(
        _chart("histogram", "Clinical trial enrollment distribution", {
            "x": {"field": "bin_start", "end_field": "bin_end", "type": "quantitative", "title": "Enrollment range (participants)"},
            "y": {"field": "trial_count", "type": "quantitative", "title": "Distinct studies"},
        }, rows),
        ("Enrollment may be estimated or actual; studies without numeric enrollment are excluded.",),
        visualized_nct_ids=frozenset(s.nct_id for s in valid),
    )


def _scatter(studies: list[Study], limit: int) -> ChartResult:
    rows = []
    for s in sorted(studies, key=lambda x: x.nct_id):
        if s.start_year is None or s.enrollment is None:
            continue
        citations = _citations([s], field_kind="year", value=s.start_year, limit=limit)
        if limit >= 2:
            citations["citations"].append({
                "nct_id": s.nct_id,
                "url": f"https://clinicaltrials.gov/study/{s.nct_id}",
                "field_path": "protocolSection.designModule.enrollmentInfo.count",
                "excerpt": str(s.enrollment),
            })
        citations["citations_complete"] = limit >= 2
        rows.append({"nct_id": s.nct_id, "year": s.start_year,
                     "enrollment": s.enrollment, **citations})
    return ChartResult(
        _chart("scatter_plot", "Enrollment versus trial start year", {
            "x": {"field": "year", "type": "quantitative", "unit": "year", "title": "Start year"},
            "y": {"field": "enrollment", "type": "quantitative", "title": "Enrollment"},
            "tooltip": {"field": "nct_id", "type": "nominal"},
        }, rows),
        ("Each point is a single NCT record with numeric enrollment and a known start year.",),
        visualized_nct_ids=frozenset(row["nct_id"] for row in rows),
    )


def build_chart(
    plan: QueryPlan, studies: list[Study], *, citation_limit: int,
    cohorts: dict[str, list[Study]] | None = None,
) -> ChartResult:
    # The public client deduplicates, but this pure builder must preserve
    # distinct-NCT semantics even when tested with repeated upstream records.
    studies = list({study.nct_id: study for study in studies}.values())
    if cohorts is not None:
        cohorts = {
            name: list({study.nct_id: study for study in group}.values())
            for name, group in cohorts.items()
        }
    if plan.intent == "time_trend":
        result = _trend(plan, studies, citation_limit)
    elif plan.intent in {
        "phase_distribution", "intervention_distribution", "status_distribution",
        "sponsor_distribution", "geography",
    }:
        result = _distribution(plan, studies, citation_limit)
    elif plan.intent == "drug_comparison":
        result = _comparison(cohorts or {}, citation_limit)
    elif plan.intent in {"sponsor_drug_network", "drug_cooccurrence_network"}:
        result = _network(plan, studies, citation_limit)
    elif plan.intent == "enrollment_histogram":
        result = _histogram(studies, citation_limit)
    elif plan.intent == "enrollment_scatter":
        result = _scatter(studies, citation_limit)
    else:
        raise ValueError(f"Unsupported visualization intent: {plan.intent}")

    context = plan.condition or (" vs ".join(plan.drugs) if plan.drugs else None)
    if context:
        return ChartResult(
            result.visualization.model_copy(update={"title": f"{result.visualization.title} — {context}"}),
            result.assumptions,
            result.visualization_truncated,
            result.visualization_total_items,
            result.visualized_nct_ids,
        )
    return result
