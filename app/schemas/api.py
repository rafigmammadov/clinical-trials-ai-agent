"""Versioned HTTP contract for inputs and visualization outputs."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Intent = Literal[
    "time_trend", "phase_distribution", "intervention_distribution",
    "status_distribution", "sponsor_distribution", "geography",
    "drug_comparison", "sponsor_drug_network", "drug_cooccurrence_network",
    "enrollment_histogram", "enrollment_scatter",
]
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
        return self


class VisualizationSpec(StrictModel):
    type: ChartType
    title: str
    encoding: dict[str, dict[str, Any]]
    data: list[dict[str, Any]] | dict[str, list[dict[str, Any]]]


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
    # For two separate cohort searches, no meaningful combined totalCount exists.
    cohort_matches: dict[str, int | None] | None = None
    # Registry completeness and visualization coverage are independent.
    visualization_truncated: bool = False
    visualization_items_returned: int | None = None
    visualization_total_items: int | None = None


class AnalyzeResponse(StrictModel):
    visualization: VisualizationSpec
    meta: ResponseMeta
