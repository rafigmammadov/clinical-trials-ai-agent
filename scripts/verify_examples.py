"""Offline quality gate for live example outputs, independent of OpenAI or registry access."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.schemas.api import AnalyzeResponse


EXPECTED = {
    "time_trend": "time_series",
    "phase_distribution": "bar_chart",
    "geography": "bar_chart",
    "network": "network_graph",
    "comparison": "grouped_bar_chart",
}


def verify_example(path: Path, expected_type: str, *, allow_partial: bool = False) -> str:
    """Raise ValueError for a broken example, otherwise return a concise summary."""
    response = AnalyzeResponse.model_validate_json(path.read_text(encoding="utf-8"))
    chart, meta = response.visualization, response.meta
    if chart.type != expected_type:
        raise ValueError(f"Unexpected chart type: {chart.type} (expected {expected_type})")
    if not allow_partial and not meta.complete:
        raise ValueError("Registry search is partial; do not submit unqualified totals")
    if not 0 < meta.records_used <= meta.records_fetched:
        raise ValueError("No contributing records or invalid record accounting")

    if chart.type == "network_graph":
        if not isinstance(chart.data, dict):
            raise ValueError("Network data must include nodes and edges")
        nodes, rows = chart.data.get("nodes", []), chart.data.get("edges", [])
        ids = [n["id"] for n in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Network has duplicate node IDs")
        for edge in rows:
            if edge["source"] not in ids or edge["target"] not in ids:
                raise ValueError("Network edge references a missing node")
            if edge["weight"] != edge["citation_count"] or edge["weight"] <= 0:
                raise ValueError("Network weight and study provenance disagree")
            for cited in edge["citations"]:
                if not cited.get("related_field_path") or not cited.get("related_excerpt"):
                    raise ValueError("Network edge lacks evidence for the second endpoint")
        if not nodes or not rows:
            raise ValueError("Network example contains no nodes or edges")
    else:
        if not isinstance(chart.data, list):
            raise ValueError("Non-network data must be an array")
        rows = chart.data
        if not rows:
            raise ValueError("Example has no data points")
        for row in rows:
            if "trial_count" in row and row["trial_count"] != row["citation_count"]:
                raise ValueError("Chart count and supporting-study count disagree")
            if row.get("trial_count", 1) < 0:
                raise ValueError("Negative trial count")
    if meta.visualization_items_returned is not None and meta.visualization_items_returned != len(rows):
        raise ValueError("Metadata rendered-item count differs from JSON data")
    if meta.visualization_truncated:
        if (meta.visualization_total_items is None
                or meta.visualization_total_items <= len(rows)
                or not meta.warnings):
            raise ValueError("Missing or inconsistent visualization truncation disclosure")
    for row in rows:
        count = row["citation_count"]
        refs = row["citations"]
        if count < 0:
            raise ValueError("Negative evidence count")
        cited_ids = {ref["nct_id"] for ref in refs}
        if len(cited_ids) > meta.citation_limit_per_datum:
            raise ValueError("Cited study count exceeds configured limit")
        if len(cited_ids) > count:
            raise ValueError("More distinct cited studies than contributing studies")
        if any(
            not ref["nct_id"].startswith("NCT")
            or not ref["url"].endswith(ref["nct_id"])
            or not ref.get("field_path")
            or not ref.get("excerpt")
            for ref in refs
        ):
            raise ValueError("Invalid citation identifier or missing source evidence")
        if meta.drug_match_mode == "registered_name" and meta.query_plan.drugs:
            from app.services.intervention_matching import NAME_FIELD, ALIAS_FIELD
            field_key, excerpt_key = (
                ("related_field_path", "related_excerpt")
                if meta.query_plan.intent == "drug_comparison" else
                ("matched_drug_field_path", "matched_drug_excerpt")
            )
            for ref in refs:
                if (ref.get(field_key) not in {NAME_FIELD, ALIAS_FIELD}
                        or not ref.get(excerpt_key)):
                    raise ValueError("Strict cohort citation lacks registered DRUG membership evidence")
    note = "TRUNCATED" if meta.visualization_truncated else "FULL CHART"
    return f"{chart.type}: {len(rows)} points/edges, {meta.records_used} studies, {note}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify actual registry-backed example JSONs")
    parser.add_argument("--directory", type=Path, default=Path("examples"))
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    for name, kind in EXPECTED.items():
        path = args.directory / f"{name}.json"
        if not path.is_file():
            parser.error(f"Missing required example: {path}")
        try:
            summary = verify_example(path, kind, allow_partial=args.allow_partial)
        except Exception as exc:
            parser.error(f"{path}: {exc}")
        print(f"PASS {path.name}: {summary}")
    print("All five examples validated successfully")


if __name__ == "__main__":
    main()
