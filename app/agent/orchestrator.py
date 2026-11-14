"""Application use case: plan -> retrieve -> normalize/filter -> aggregate -> render."""

import asyncio
import re
from datetime import date, datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.agent.planner import Planner
from app.agent.grounding import validate_plan_grounding
from app.agent.recall import validate_plan_recall
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, AnalyzeResponse, DrugMatchMode, QueryPlan, ResponseMeta
from app.services.intervention_matching import find_registered_drug_match
from app.services.clinicaltrials import ClinicalTrialsClient
from app.services.normalizer import Study
from app.visualizations.builder import build_chart


def is_future_study_start(study: Study, today: date) -> bool:
    """Exclude known future start dates, including future YYYY-MM months."""
    if study.start_year is not None and study.start_year > today.year:
        return True
    if study.start_date and len(study.start_date) == 7:
        # YYYY-MM is sufficient to exclude a known future month; a missing
        # day within the current month does not establish a future start.
        year, month = (int(part) for part in study.start_date.split("-"))
        return (year, month) > (today.year, today.month)
    if study.start_date:
        try:
            return date.fromisoformat(study.start_date) > today
        except ValueError:
            # ClinicalTrials.gov may return YYYY-MM or YYYY for partial dates.
            return False
    return False


class AnalysisService:
    def __init__(self, planner: Planner, trials: ClinicalTrialsClient) -> None:
        self._planner = planner
        self._trials = trials

    @staticmethod
    def _merge(plan: QueryPlan, request: AnalyzeRequest) -> QueryPlan:
        overrides = {
            key: getattr(request, key)
            for key in ("condition", "drugs", "sponsor", "country", "start_year", "end_year", "recruiting_only")
            if getattr(request, key) is not None
        }
        try:
            return QueryPlan.model_validate({**plan.model_dump(), **overrides})
        except ValidationError as exc:
            raise QueryError(
                "Explicit request filters conflict with the AI plan; "
                "provide a consistent date range or clarify the question"
            ) from exc

    @staticmethod
    def _reconcile_end_year(plan: QueryPlan, request: AnalyzeRequest) -> tuple[QueryPlan, str | None]:
        """Do not accept a model-imagined upper date bound as a user constraint.

        Explicit structured filters take precedence. Only a single unbounded
        `since YYYY` request can be repaired deterministically; other unexplained
        model-supplied dates fail closed rather than silently changing the cohort.
        """
        if request.end_year is not None or plan.end_year is None:
            return plan, None

        explicit_years = {
            int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", request.query)
        }
        if plan.end_year in explicit_years:
            return plan, None

        start_year = request.start_year if request.start_year is not None else plan.start_year
        is_unbounded_since = (
            plan.intent == "time_trend"
            and start_year is not None
            and explicit_years == {start_year}
            and re.search(rf"\bsince\s+{start_year}\b", request.query, re.I)
            and not re.search(
                r"\b(?:through|until|ending|before|prior|up to|last year)\b",
                request.query, re.I,
            )
        )
        if not is_unbounded_since:
            raise QueryError(
                "The AI planner supplied an end year not stated in the question; "
                "specify end_year explicitly or use an explicit year range"
            )
        warning = (
            f"The AI planner inferred end_year={plan.end_year} without support in "
            "the question; the unsupported end-year restriction was removed"
        )
        interpretation = (
            f"Count clinical trial starts by year since {start_year}, without an "
            "end-year cap; other validated filters remain applicable."
        )
        return plan.model_copy(update={
            "end_year": None, "interpretation": interpretation,
        }), warning

    @staticmethod
    def _post_filter(
        studies: tuple[Study, ...], plan: QueryPlan, *, drug: str | None = None,
        drug_match_mode: DrugMatchMode = "registry_text",
    ) -> list[Study]:
        """Apply local date/status/country/lead-sponsor filters.

        Condition and intervention terms still rely on registry text search;
        this is not canonical disease or drug identity resolution.
        """
        chosen = []
        for study in studies:
            if (drug_match_mode == "registered_name" and drug is not None
                    and find_registered_drug_match(study, drug) is None):
                continue
            if plan.start_year is not None and (study.start_year is None or study.start_year < plan.start_year):
                continue
            if plan.end_year is not None and (study.start_year is None or study.start_year > plan.end_year):
                continue
            if (plan.intent == "time_trend" and plan.end_year is None and
                    is_future_study_start(study, datetime.now(timezone.utc).date())):
                continue
            if plan.recruiting_only and study.status != "RECRUITING":
                continue
            if plan.country and not any(x.casefold() == plan.country.casefold() for x in study.countries):
                continue
            # query.spons can also match collaborator; 'sponsor' here explicitly means lead sponsor.
            if plan.sponsor and (not study.sponsor or plan.sponsor.casefold() not in study.sponsor.casefold()):
                continue
            chosen.append(study)
        return chosen

    async def analyze(self, request: AnalyzeRequest) -> AnalyzeResponse:
        inferred_plan = await self._planner.plan(request.query)
        if inferred_plan.intent == "unsupported":
            raise QueryError("The requested analysis is unsupported; ask a question about clinical trial counts, distributions or relationships")
        inferred_plan, temporal_warning = self._reconcile_end_year(inferred_plan, request)
        plan = self._merge(inferred_plan, request)
        plan = validate_plan_grounding(plan, request)
        plan = validate_plan_recall(plan, request)
        if request.drug_match_mode == "registered_name" and not plan.drugs:
            raise QueryError("registered_name drug matching requires a named drug filter")
        if plan.intent == "drug_comparison":
            if len(plan.drugs) != 2 or plan.drugs[0].casefold() == plan.drugs[1].casefold():
                raise QueryError("Drug comparisons require exactly two distinct drug names")
        elif len(plan.drugs) > 1:
            raise QueryError("Only drug comparisons accept more than one named drug filter")

        if plan.intent == "drug_comparison":
            found = await asyncio.gather(*(
                self._trials.search(plan, max_studies=request.max_studies, drug=drug)
                for drug in plan.drugs
            ))
            cohorts = {
                drug: self._post_filter(
                    result.studies, plan, drug=drug,
                    drug_match_mode=request.drug_match_mode,
                )
                for drug, result in zip(plan.drugs, found)
            }
            studies_by_id = {s.nct_id: s for group in cohorts.values() for s in group}
            studies = list(studies_by_id.values())
            fetched_count = len({s.nct_id for result in found for s in result.studies})
            complete = all(result.complete for result in found)
            warnings = list(dict.fromkeys(w for result in found for w in result.warnings))
            cohort_matches = {drug: result.total_matches for drug, result in zip(plan.drugs, found)}
            total_matches = None
            if any(len(cohorts[drug]) == 0 for drug in plan.drugs):
                warnings.append("One or more comparison cohorts have no matching normalized studies")
        else:
            result = await self._trials.search(
                plan, max_studies=request.max_studies, drug=plan.drugs[0] if plan.drugs else None
            )
            studies = self._post_filter(
                result.studies, plan,
                drug=plan.drugs[0] if plan.drugs else None,
                drug_match_mode=request.drug_match_mode,
            )
            fetched_count = len(result.studies)
            cohorts = None
            complete = result.complete
            warnings = list(result.warnings)
            total_matches = result.total_matches
            cohort_matches = None

        if temporal_warning is not None:
            warnings.append(temporal_warning)
        if not studies:
            warnings.append("No matching study records were available for this analysis")
            if plan.drugs and request.drug_match_mode == "registered_name":
                warnings.append(
                    "No returned candidate has the requested registered DRUG name or otherNames; "
                    "this does not prove that no such trials exist in the registry"
                )
        if not complete:
            warnings.append("This visualization is based on incomplete records and must not be read as a complete population count")
        if request.citation_limit == 0:
            warnings.append("Per-datum citations were disabled by citation_limit=0")
        chart = build_chart(
            plan, studies, citation_limit=request.citation_limit, cohorts=cohorts,
            drug_match_mode=request.drug_match_mode,
        )
        if chart.visualization_truncated:
            rendered_count = (
                len(chart.visualization.data["edges"])
                if chart.visualization.type == "network_graph"
                else len(chart.visualization.data)
            )
            item_name = "edges" if chart.visualization.type == "network_graph" else "categories"
            warnings.append(
                f"Visualization displays only {rendered_count} of "
                f"{chart.visualization_total_items} {item_name}; "
                "complete registry retrieval does not mean complete visualization coverage"
            )
        # Post-filter records can lack fields needed for the selected chart.
        # Keep historical records_used semantics while disclosing actual support.
        visualized_count = len(chart.visualized_nct_ids)
        not_visualized_count = len(studies) - visualized_count
        if not_visualized_count > 0:
            warnings.append(
                f"{not_visualized_count} post-filter studies did not contribute to the "
                "displayed visualization (missing chart fields or display limits)"
            )
        assumptions = list(chart.assumptions)
        if plan.drugs and request.drug_match_mode == "registered_name":
            assumptions.append(
                "Registered-name mode verifies DRUG intervention names and otherNames "
                "in retrieved records using case-insensitive, whitespace-normalized equality. "
                "It is not drug ontology resolution and cannot recover candidates absent "
                "from the upstream registry text search."
            )
        if plan.intent != "drug_comparison" and plan.drugs:
            assumptions.append("Intervention search uses registry text matching, not exact drug-name identity resolution.")
        if plan.start_year or plan.end_year:
            assumptions.append("Start-year filters apply to study start dates, not registration or publication dates.")
        if plan.intent == "time_trend" and plan.end_year is None:
            assumptions.append("With no end year, known future calendar dates are excluded; partial or estimated dates do not establish verified trial starts.")
        matched_drug_counts = None
        if plan.drugs and request.drug_match_mode == "registered_name":
            matched_drug_counts = (
                {drug: len(cohorts[drug]) for drug in plan.drugs}
                if cohorts is not None else {plan.drugs[0]: len(studies)}
            )
        filters: dict[str, Any] = {
            key: value for key, value in plan.model_dump(exclude={"intent", "interpretation"}).items()
            if value is not None and value != []
        }
        if plan.drugs:
            filters["drug_match_mode"] = request.drug_match_mode
        return AnalyzeResponse(
            visualization=chart.visualization,
            meta=ResponseMeta(
                analyzed_at=datetime.now(timezone.utc), query_plan=plan,
                filters=filters, records_fetched=fetched_count, records_used=len(studies),
                total_matches=total_matches, complete=complete,
                warnings=warnings, assumptions=assumptions,
                citation_limit_per_datum=request.citation_limit,
                cohort_matches=cohort_matches,
                drug_match_mode=request.drug_match_mode,
                matched_drug_counts=matched_drug_counts,
                visualization_truncated=chart.visualization_truncated,
                visualization_total_items=chart.visualization_total_items,
                records_visualized=visualized_count,
                records_not_visualized=not_visualized_count,
                visualization_items_returned=(
                    len(chart.visualization.data["edges"])
                    if chart.visualization.type == "network_graph"
                    else len(chart.visualization.data)
                ),
            ),
        )
