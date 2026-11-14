"""Independent offline omission-detection benchmark for planner query filters.

Synthetic plans and user questions, NOT clinical registry records or real model
outputs. Guard recall below is detection recall *on this labeled fixture set*,
not measured OpenAI query-plan recall; see evals.run --mode live for the latter.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from app.agent.recall import missing_question_filters
from app.schemas.api import AnalyzeRequest, QueryPlan

CASES = Path(__file__).with_name("recall_cases.json")
FIELDS = {"condition", "drugs", "country", "sponsor", "start_year", "end_year", "recruiting_only"}


def run_benchmark() -> dict:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    ids = [case["id"] for case in cases]
    if not cases or not all(ids) or len(set(ids)) != len(ids):
        raise ValueError("Recall benchmark identifiers must be unique and non-empty")
    failures = []
    by_category: dict[str, Counter] = {}
    tp = fp = fn = tn = 0
    for case in cases:
        expectation = set(case["expected_missing"])
        if not expectation <= FIELDS:
            raise ValueError(f"Unknown expected_missing field in {case['id']}")
        request = AnalyzeRequest(query=case["question"], **case.get("overrides", {}))
        plan = QueryPlan.model_validate(case["plan"])
        # Use the actual request-merge logic to simulate service behavior.
        from app.agent.orchestrator import AnalysisService
        plan = AnalysisService._merge(plan, request)
        actual = set(missing_question_filters(plan, request))
        cat = by_category.setdefault(case["category"], Counter())
        cat["total"] += 1
        cat["passed"] += actual == expectation
        tp += len(actual & expectation)
        fp += len(actual - expectation)
        fn += len(expectation - actual)
        if not expectation and not actual:
            tn += 1
        if actual != expectation:
            failures.append({
                "id": case["id"], "expected_missing": sorted(expectation),
                "actual_missing": sorted(actual),
            })
    return {
        "fixture_type": "synthetic_omitted_filter_plans",
        "total": len(cases), "passed": len(cases) - len(failures),
        "omission_detection_recall": tp / (tp + fn) if tp + fn else None,
        "omission_detection_precision": tp / (tp + fp) if tp + fp else None,
        "unrestricted_true_negatives": tn,
        "by_category": {name: dict(stats) for name, stats in sorted(by_category.items())},
        "failures": failures,
    }


def main() -> None:
    report = run_benchmark()
    print(json.dumps(report, indent=2))
    if report["failures"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
