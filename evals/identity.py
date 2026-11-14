"""Offline, hand-labeled intervention identity benchmark with synthetic records.

No registry queries or OpenAI calls occur. This measures the conservative
matching policy, NOT the recall of the upstream ClinicalTrials.gov search.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.intervention_matching import (
    ALIAS_FIELD, NAME_FIELD, find_registered_drug_match,
)
from app.services.normalizer import normalize_study

CASE_PATH = Path(__file__).with_name("identity_cases.json")
FIELD_TAGS = {"name": NAME_FIELD, "alias": ALIAS_FIELD, None: None}


def evaluate_cases(path: Path = CASE_PATH) -> dict[str, object]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("Identity benchmark must contain a nonempty list")
    seen = set()
    results = []
    for index, case in enumerate(cases, start=1):
        identifier = case["id"]
        if identifier in seen:
            raise ValueError(f"Duplicate identity case: {identifier}")
        seen.add(identifier)
        expected_tag = case["expected_field"]
        if expected_tag not in FIELD_TAGS:
            raise ValueError(f"Invalid expected field in case {identifier}")
        raw = {
            "protocolSection": {
                "identificationModule": {"nctId": f"NCT{index:08d}"},
                "armsInterventionsModule": {"interventions": case["interventions"]},
            }
        }
        study = normalize_study(raw)
        matched = find_registered_drug_match(study, case["term"])
        expected_path = FIELD_TAGS[expected_tag]
        passed = (
            (matched.field_path if matched else None) == expected_path
            and (matched.excerpt if matched else None) == case["expected_excerpt"]
        )
        results.append({"id": identifier, "passed": passed})
    return {
        "fixture_type": "synthetic_registered_interventions",
        "total": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed_ids": [result["id"] for result in results if not result["passed"]],
    }


def main() -> None:
    report = evaluate_cases()
    print(json.dumps(report, indent=2))
    if report["failed_ids"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
