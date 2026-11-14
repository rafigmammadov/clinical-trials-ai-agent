"""Application use case: plan -> retrieve -> normalize/filter -> aggregate -> render."""

import asyncio
from datetime import date, datetime, timezone
from typing import Any

from app.agent.planner import Planner
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, AnalyzeResponse, QueryPlan, ResponseMeta
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
        return QueryPlan.model_validate({**plan.model_dump(), **overrides})

    @staticmethod
    def _post_filter(studies: tuple[Study, ...], plan: QueryPlan) -> list[Study]:
        """Apply local date/status/country/lead-sponsor filters.

        Condition and intervention terms still rely on registry text search;
        this is not canonical disease or drug identity resolution.
        """
        chosen = []
        for study in studies:
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
        plan = self._merge(await self._planner.plan(request.query), request)
        if plan.intent == "unsupported":
            raise QueryError("The requested analysis is unsupported; ask a question about clinical trial counts, distributions or relationships")
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
                drug: self._post_filter(result.studies, plan)
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
            studies = self._post_filter(result.studies, plan)
            fetched_count = len(result.studies)
            cohorts = None
            complete = result.complete
            warnings = list(result.warnings)
            total_matches = result.total_matches
            cohort_matches = None

        if not studies:
            warnings.append("No matching study records were available for this analysis")
        if not complete:
            warnings.append("This visualization is based on incomplete records and must not be read as a complete population count")
        if request.citation_limit == 0:
            warnings.append("Per-datum citations were disabled by citation_limit=0")
        chart = build_chart(plan, studies, citation_limit=request.citation_limit, cohorts=cohorts)
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
        if plan.intent != "drug_comparison" and plan.drugs:
            assumptions.append("Intervention search uses registry text matching, not exact drug-name identity resolution.")
        if plan.start_year or plan.end_year:
            assumptions.append("Start-year filters apply to study start dates, not registration or publication dates.")
        if plan.intent == "time_trend" and plan.end_year is None:
            assumptions.append("With no end year, known future calendar dates are excluded; partial or estimated dates do not establish verified trial starts.")
        filters: dict[str, Any] = {
            key: value for key, value in plan.model_dump(exclude={"intent", "interpretation"}).items()
            if value is not None and value != []
        }
        return AnalyzeResponse(
            visualization=chart.visualization,
            meta=ResponseMeta(
                analyzed_at=datetime.now(timezone.utc), query_plan=plan,
                filters=filters, records_fetched=fetched_count, records_used=len(studies),
                total_matches=total_matches, complete=complete,
                warnings=warnings, assumptions=assumptions,
                citation_limit_per_datum=request.citation_limit,
                cohort_matches=cohort_matches,
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
