"""Offline labeled evaluation of the plan-to-question lexical grounding guard.

The cases intentionally simulate model output. They neither measure OpenAI
accuracy nor make requests to ClinicalTrials.gov, and they contain no patient
data or genuine trial-count claims.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.agent.grounding import validate_plan_grounding
from app.agent.orchestrator import AnalysisService
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan

CASES = Path(__file__).with_name("grounding_cases.json")


def run_benchmark() -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    ids = [row["id"] for row in cases]
    if not cases or len(ids) != len(set(ids)):
        raise ValueError("Grounding benchmark must have unique non-empty case identifiers")
    failed = []
    category_totals = Counter()
    category_passes = Counter()
    for row in cases:
        if row["expected"] not in ("allow", "reject"):
            raise ValueError(f"Unknown expected decision in {row['id']}")
        request = AnalyzeRequest(query=row["question"], **row.get("overrides", {}))
        plan = AnalysisService._merge(QueryPlan.model_validate(row["plan"]), request)
        try:
            validate_plan_grounding(plan, request)
            actual = "allow"
        except QueryError:
            actual = "reject"
        category_totals[row["category"]] += 1
        category_passes[row["category"]] += actual == row["expected"]
        if actual != row["expected"]:
            failed.append({"id": row["id"], "expected": row["expected"], "actual": actual})
    return {
        "fixture_type": "synthetic_model_query_plans",
        "total": len(cases), "passed": len(cases) - len(failed),
        "by_category": {
            category: {"passed": category_passes[category], "total": category_totals[category]}
            for category in sorted(category_totals)
        },
        "failures": failed,
    }


def main() -> None:
    result = run_benchmark()
    print(json.dumps(result, indent=2))
    if result["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
