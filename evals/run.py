"""Planner benchmark: schema verification offline, optional live GPT evaluation.

No live or paid calls are made unless --mode live is explicitly selected.
A mismatch is a reported observation, not an automatically 'fixed' ground truth.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter, defaultdict, deque
from pathlib import Path

from app.agent.planner import OpenAIPlanner
from app.agent.orchestrator import AnalysisService
from app.errors import QueryError, PlanningError
from app.config import get_settings
from app.schemas.api import QueryPlan, AnalyzeRequest

DATASET = Path(__file__).with_name("cases.json")


def load_cases() -> list[dict]:
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    ids = [case["id"] for case in data]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate benchmark case identifiers")
    for case in data:
        QueryPlan(intent=case["intent"], **case["fields"])
        if not case["question"].strip():
            raise ValueError(f"Empty question in {case['id']}")
    return data


def balanced_sample(cases: list[dict], limit: int) -> list[dict]:
    """Interleave query families, not just the first easy cases."""
    groups: dict[str, deque] = defaultdict(deque)
    for case in cases:
        groups[case["category"]].append(case)
    selected = []
    while len(selected) < limit and any(groups.values()):
        for category in sorted(groups):
            if groups[category] and len(selected) < limit:
                selected.append(groups[category].popleft())
    return selected


def matches(field: str, actual, expected) -> bool:
    if field == "country" and isinstance(actual, str) and isinstance(expected, str):
        from app.agent.grounding import _canonical_country
        return _canonical_country(actual).casefold() == _canonical_country(expected).casefold()
    if field == "drugs" and isinstance(actual, list) and isinstance(expected, list):
        return sorted(v.strip().casefold() for v in actual) == sorted(v.strip().casefold() for v in expected)
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().casefold() == expected.strip().casefold()
    return actual == expected


def positive_requested_filters(fields: dict) -> set[str]:
    """Only positively labeled constraints belong in the recall denominator.

    Missing/empty/null expected fields and `recruiting_only=False` are not
    requested positive retrieval restrictions. This is an evaluation over
    annotated fields, not a full extraction of all semantic requirements.
    """
    return {name for name, expected in fields.items()
            if name in {"condition", "drugs", "sponsor", "country", "start_year", "end_year", "recruiting_only"}
            and expected is not None and expected is not False and expected != [] and expected != ""}


async def run_live(cases: list[dict], model: str, key: str) -> dict:
    """Measure intent and explicitly labeled filters; never infer accuracy from JSON alone."""
    planner = OpenAIPlanner(api_key=key, model=model)
    results = []
    try:
        for case in cases:
            try:
                actual = await planner.plan(case["question"])
                observed = actual.model_dump()
                intent_correct = actual.intent == case["intent"]
                checked = {
                    name: matches(name, getattr(actual, name), expected)
                    for name, expected in case["fields"].items()
                }
                requested = positive_requested_filters(case["fields"])
                results.append({
                    "id": case["id"], "category": case["category"],
                    "expected_intent": case["intent"], "observed": observed,
                    "schema_valid": True, "intent_correct": intent_correct,
                    "checked_filters": checked,
                    "requested_filter_results": {name: checked[name] for name in sorted(requested)},
                })
            except Exception as exc:
                # Keep private provider exception content out of reports.
                results.append({
                    "id": case["id"], "category": case["category"],
                    "schema_valid": False, "error_type": type(exc).__name__,
                    "intent_correct": False, "checked_filters": {},
                    "requested_filter_results": {
                        name: False for name in sorted(positive_requested_filters(case["fields"]))
                    },
                })
    finally:
        await planner.close()

    def score(group: list[dict]) -> dict:
        checked = [v for row in group for v in row["checked_filters"].values()]
        requested = [v for row in group for v in row["requested_filter_results"].values()]
        return {
            "evaluated": len(group),
            "schema_valid_rate": sum(row["schema_valid"] for row in group) / len(group) if group else None,
            "intent_accuracy": sum(row["intent_correct"] for row in group) / len(group) if group else None,
            "evaluated_filter_assertions": len(checked),
            "filter_accuracy": sum(checked) / len(checked) if checked else None,
            "requested_filter_assertions": len(requested),
            "requested_filter_recall": sum(requested) / len(requested) if requested else None,
        }

    categories = sorted({row["category"] for row in results})
    overall = score(results)
    return {
        "mode": "live", "model": model,
        **overall,
        "by_category": {
            category: score([row for row in results if row["category"] == category])
            for category in categories
        },
        "results": results,
    }


async def run_guarded(cases: list[dict], model: str, key: str) -> dict:
    """Evaluate the *runtime* plan guard and one-repair flow; no registry calls.

    The expected decision is to reject 'unsupported' cases and accept supported
    cases only after full deterministic validation. This is a planning benchmark,
    not a clinical data accuracy test.
    """
    planner = OpenAIPlanner(api_key=key, model=model)

    class ForbiddenRegistry:
        async def search(self, *_args, **_kwargs):
            raise AssertionError("Guarded planner eval must never retrieve clinical data")

    service = AnalysisService(planner, ForbiddenRegistry())
    rows = []
    try:
        for case in cases:
            try:
                plan, _warning, attempts = await service._plan_with_one_repair(
                    AnalyzeRequest(query=case["question"])
                )
                rows.append({
                    "id": case["id"], "category": case["category"],
                    "accepted": True, "attempts": attempts,
                    "intent_correct": plan.intent == case["intent"],
                    "observed_intent": plan.intent,
                })
            except (QueryError, PlanningError) as exc:
                rows.append({
                    "id": case["id"], "category": case["category"],
                    "accepted": False, "attempts": None,
                    "intent_correct": case["intent"] == "unsupported",
                    "error_type": type(exc).__name__,
                    # Safe application validation feedback helps reproduce
                    # false rejections without guessing from a bare type.
                    "error_detail": str(exc)[:400],
                })
    finally:
        await planner.close()
    decisions = [row["accepted"] == (case["intent"] != "unsupported")
                 for row, case in zip(rows, cases)]
    return {
        "mode": "guarded", "model": model, "evaluated": len(rows),
        "guard_decision_accuracy": sum(decisions) / len(decisions) if decisions else None,
        "accepted": sum(row["accepted"] for row in rows),
        "rejected": sum(not row["accepted"] for row in rows),
        "repaired": sum(row["attempts"] == 2 for row in rows),
        "results": rows,
        "note": "Guarded evaluation runs model planning only; no ClinicalTrials.gov calls or count verification",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run validated query-planner benchmark")
    parser.add_argument("--mode", choices=["validate", "live", "guarded"], default="validate")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--category", default=None, help="Optional family to evaluate")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    cases = load_cases()
    categories = dict(sorted(Counter(c["category"] for c in cases).items()))
    print(f"Benchmark: {len(cases)} schema-valid cases; categories={categories}")
    if args.mode == "validate":
        print("No live model calls made; semantic accuracy not measured")
        return
    if args.category:
        cases = [case for case in cases if case["category"] == args.category]
        if not cases:
            parser.error("No cases for that category")
    if not 1 <= args.limit <= len(cases):
        parser.error(f"--limit must be between 1 and {len(cases)}")
    settings = get_settings()
    if not settings.openai_api_key:
        parser.error("A rotated OPENAI_API_KEY is required for --mode live")
    chosen = balanced_sample(cases, args.limit)
    if args.mode == "guarded":
        report = asyncio.run(run_guarded(chosen, settings.openai_model, settings.openai_api_key))
    else:
        report = asyncio.run(run_live(chosen, settings.openai_model, settings.openai_api_key))
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote report: {args.output}")


if __name__ == "__main__":
    main()
