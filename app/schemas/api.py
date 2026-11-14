"""Versioned HTTP contract for inputs and visualization outputs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Intent = Literal[
    "time_trend", "phase_distribution", "intervention_distribution",
    "status_distribution", "sponsor_distribution", "geography",
    "drug_comparison", "sponsor_drug_network", "drug_cooccurrence_network",
    "enrollment_histogram", "enrollment_scatter", "unsupported",
]
DrugMatchMode = Literal["registry_text", "registered_name"]
ChartType = Literal[
    "time_series", "bar_chart", "grouped_bar_chart", "network_graph",
    "histogram", "scatter_plot",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(StrictModel):
    query: str = Field(min_length=5, max_length=2000)
    condition: str | None = Field(default=None, max_length=200)
    drugs: list[str] | None = Field(default=None, max_length=3)
    sponsor: str | None = Field(default=None, max_length=200)
    country: str | None = Field(default=None, max_length=100)
    start_year: int | None = Field(default=None, ge=1900, le=2100)
    end_year: int | None = Field(default=None, ge=1900, le=2100)
    recruiting_only: bool | None = None
    drug_match_mode: DrugMatchMode = "registry_text"
    max_studies: int = Field(default=1000, ge=1, le=5000)
    citation_limit: int = Field(default=10, ge=0, le=50)

    @field_validator("query")
    @classmethod
    def validate_nonblank_question(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 5:
            raise ValueError("query must contain at least 5 non-whitespace characters")
        return cleaned

    @field_validator("condition", "sponsor", "country")
    @classmethod
    def validate_nonblank_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("filter cannot be whitespace-only")
        return cleaned

    @field_validator("drugs")
    @classmethod
    def normalize_drug_names(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("drugs must contain non-empty names")
        return cleaned

    @model_validator(mode="after")
    def check_years(self) -> "AnalyzeRequest":
        if self.start_year and self.end_year and self.start_year > self.end_year:
            raise ValueError("start_year must be <= end_year")
        if self.drugs is not None and any(not d.strip() for d in self.drugs):
            raise ValueError("drugs must contain non-empty names")
        return self


class QueryPlan(StrictModel):
    """The ONLY content the LLM is allowed to produce."""

    intent: Intent
    condition: str | None = None
    drugs: list[str] = Field(default_factory=list)
    sponsor: str | None = None
    country: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    recruiting_only: bool = False
    interpretation: str = ""

    @field_validator("condition", "sponsor", "country")
    @classmethod
    def clean_optional_term(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

    @field_validator("drugs")
    @classmethod
    def clean_drug_terms(cls, value: list[str]) -> list[str]:
        return [name.strip() for name in value]

    @model_validator(mode="after")
    def validate_plan(self) -> "QueryPlan":
        if self.start_year is not None and not 1900 <= self.start_year <= 2100:
            raise ValueError("start_year is outside the allowed range")
        if self.end_year is not None and not 1900 <= self.end_year <= 2100:
            raise ValueError("end_year is outside the allowed range")
        if (self.start_year is not None and self.end_year is not None
                and self.start_year > self.end_year):
            raise ValueError("start_year must be <= end_year")
        if len(self.drugs) > 3 or any(not x.strip() for x in self.drugs):
            raise ValueError("at most 3 non-empty drug names are permitted")
        # Defense-in-depth: structured request filters have their own limits,
        # but model-generated fields bypass AnalyzeRequest validation.
        for name, limit in (("condition", 200), ("sponsor", 200),
                            ("country", 100), ("interpretation", 500)):
            value = getattr(self, name)
            if value is not None and len(value) > limit:
                raise ValueError(f"{name} exceeds the permitted length")
        if any(len(drug) > 200 for drug in self.drugs):
            raise ValueError("drug name exceeds the permitted length")
        return self


class VisualizationSpec(StrictModel):
    """Renderer contract; verify that specified channels exist in actual data."""

    type: ChartType
    title: str = Field(min_length=1)
    encoding: dict[str, dict[str, Any]]
    data: list[dict[str, Any]] | dict[str, list[dict[str, Any]]]

    @model_validator(mode="after")
    def validate_renderer_contract(self) -> "VisualizationSpec":
        if self.type == "network_graph":
            if not isinstance(self.data, dict) or set(self.data) != {"nodes", "edges"}:
                raise ValueError("network_graph data must contain nodes and edges")
            if not {"nodes", "edges"}.issubset(self.encoding):
                raise ValueError("network_graph encoding requires nodes and edges")
            ids = []
            for node in self.data["nodes"]:
                if not isinstance(node.get("id"), str) or not node["id"]:
                    raise ValueError("network node requires a non-empty string id")
                ids.append(node["id"])
            if len(ids) != len(set(ids)):
                raise ValueError("network node ids must be unique")
            valid_ids = set(ids)
            for edge in self.data["edges"]:
                if edge.get("source") not in valid_ids or edge.get("target") not in valid_ids:
                    raise ValueError("network edge references an unknown node")
                weight = edge.get("weight")
                if type(weight) is not int or weight < 1:
                    raise ValueError("network edge weight must be a positive integer")
            return self

        if not isinstance(self.data, list):
            raise ValueError("non-network chart data must be a row array")
        if "x" not in self.encoding or "y" not in self.encoding:
            raise ValueError("chart encoding must contain x and y channels")
        for channel in ("x", "y", "color", "tooltip"):
            if channel not in self.encoding:
                continue
            spec = self.encoding[channel]
            fields = (spec.get("field"), spec.get("end_field"))
            for field in (x for x in fields if x is not None):
                if not isinstance(field, str) or not field:
                    raise ValueError(f"encoding {channel} requires a field name")
                if any(field not in row for row in self.data):
                    raise ValueError(f"encoding {channel} references missing field {field}")
        for row in self.data:
            count = row.get("trial_count")
            if count is not None and (type(count) is not int or count < 0):
                raise ValueError("trial_count must be a non-negative integer")
        return self


class ResponseMeta(StrictModel):
    source: str = "ClinicalTrials.gov API v2"
    source_url: str = "https://clinicaltrials.gov/data-api/api"
    analyzed_at: datetime
    query_plan: QueryPlan
    filters: dict[str, Any]
    records_fetched: int
    records_used: int
    total_matches: int | None
    complete: bool
    warnings: list[str]
    assumptions: list[str]
    citation_limit_per_datum: int
    planner_attempts: int = Field(default=1, ge=1, le=2)
    planner_repaired: bool = False
    # For two separate cohort searches, no meaningful combined totalCount exists.
    cohort_matches: dict[str, int | None] | None = None
    drug_match_mode: DrugMatchMode = "registry_text"
    matched_drug_counts: dict[str, int] | None = None
    # Registry completeness and visualization coverage are independent.
    visualization_truncated: bool = False
    visualization_items_returned: int | None = None
    visualization_total_items: int | None = None
    # Count distinct NCT IDs actually represented by a displayed chart datum/edge.
    # records_used retains its original meaning: matched post-filter records.
    records_visualized: int | None = None
    records_not_visualized: int | None = None

    @model_validator(mode="after")
    def validate_accounting(self) -> "ResponseMeta":
        if self.planner_repaired != (self.planner_attempts == 2):
            raise ValueError("planner_repaired must reflect planner_attempts")
        for field in ("records_fetched", "records_used", "citation_limit_per_datum"):
            if getattr(self, field) < 0:
                raise ValueError(f"{field} must be non-negative")
        if self.records_used > self.records_fetched:
            raise ValueError("records_used cannot exceed records_fetched")
        if self.records_visualized is not None:
            if not 0 <= self.records_visualized <= self.records_used:
                raise ValueError("records_visualized must be between zero and records_used")
            if (self.records_not_visualized is not None and
                    self.records_not_visualized != self.records_used - self.records_visualized):
                raise ValueError("records_not_visualized must equal records_used minus records_visualized")
        if self.visualization_truncated:
            if (self.visualization_total_items is None or
                    self.visualization_items_returned is None or
                    self.visualization_items_returned >= self.visualization_total_items):
                raise ValueError("visualization truncation requires a larger total-items count")
        if self.drug_match_mode == "registry_text" and self.matched_drug_counts is not None:
            raise ValueError("Text search mode cannot claim verified matched drug counts")
        if self.drug_match_mode == "registered_name" and self.query_plan.drugs:
            if (self.matched_drug_counts is None or
                    set(self.matched_drug_counts) != set(self.query_plan.drugs)):
                raise ValueError("Strict matching requires counts for each requested drug")
            if any(type(count) is not int or count < 0 or count > self.records_used
                   for count in self.matched_drug_counts.values()):
                raise ValueError("Strict drug cohort counts must be valid post-filter study counts")
        return self


class AnalyzeResponse(StrictModel):
    visualization: VisualizationSpec
    meta: ResponseMeta

    @model_validator(mode="after")
    def check_item_count(self) -> "AnalyzeResponse":
        actual = (len(self.visualization.data["edges"])
                  if self.visualization.type == "network_graph"
                  else len(self.visualization.data))
        recorded = self.meta.visualization_items_returned
        if recorded is not None and recorded != actual:
            raise ValueError("visualization_items_returned must equal the number of output rows/edges")
        return self
