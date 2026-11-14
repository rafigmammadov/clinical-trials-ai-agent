"""Fail-closed evidence checks on model-supplied retrieval restrictions.

This is a deliberately conservative lexical guard, not a clinical entity parser.
The service accepts unverified fields only when the caller independently supplies
those exact fields as typed request overrides. Unsupported paraphrases should
be clarified or provided as structured filters, not silently queried.
"""

import re
import unicodedata

from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan


# Small, explicit geographic abbreviation groups, not a country ontology.
# Group membership permits a canonical country name or its common abbreviation,
# never a city/institution inference.
COUNTRY_ALIASES: tuple[tuple[str, ...], ...] = (
    ("united states", "united states of america", "usa", "u s a", "us", "u s"),
    ("united kingdom", "uk", "u k"),
)

def _words(value: str) -> str:
    """NFKC, case folding and punctuation separators, with token boundaries."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _contains_phrase(question: str, term: str) -> bool:
    haystack, needle = _words(question), _words(term)
    return bool(needle) and f" {needle} " in f" {haystack} "


def _is_excluded(question: str, term: str) -> bool:
    """Recognize simple explicit exclusions; do not turn them into inclusions.

    This handles local negative phrases only, not general semantic negation.
    """
    phrase = _words(term)
    if not phrase:
        return False
    pattern = (
        r"(?:^|\s)(?:non|not|no|without|excluding|exclude|except|outside|other\s+than)"
        rf"\s+(?:\w+\s+){{0,2}}{re.escape(phrase)}(?:$|\s)"
    )
    return re.search(pattern, _words(question)) is not None


def _country_terms(country: str) -> tuple[str, ...]:
    normalized = _words(country)
    return next((group for group in COUNTRY_ALIASES if normalized in group), (country,))


def _country_term_present(question: str, term: str) -> bool:
    if _words(term) in ("us", "u s"):
        # A lower-case 'us' normally means a pronoun, not the country.
        return re.search(r"(?<!\w)U(?:\.)?S\.?(?!\w)", question) is not None
    return _contains_phrase(question, term)


def _country_present(question: str, country: str) -> bool:
    return any(_country_term_present(question, term) for term in _country_terms(country))


def _country_excluded(question: str, country: str) -> bool:
    return any(_is_excluded(question, term) for term in _country_terms(country))


def _canonical_country(country: str) -> str:
    normalized = _words(country)
    for group in COUNTRY_ALIASES:
        if normalized in group:
            return "United States" if group[0] == "united states" else "United Kingdom"
    return country

def _positive_recruiting_request(question: str) -> bool:
    if re.search(
        r"\b(?:non[\s-]*recruiting|not\s+(?:currently\s+)?recruiting|"
        r"excluding\s+recruiting|without\s+recruiting|"
        r"no\s+longer\s+recruiting|no\s+recruiting)\b",
        question, re.IGNORECASE,
    ):
        return False
    return bool(re.search(
        r"\b(?:recruiting|currently\s+enrolling|now\s+enrolling|"
        r"open\s+for\s+enrollment|actively\s+enrolling)\b",
        question, re.IGNORECASE,
    ))


def validate_plan_grounding(plan: QueryPlan, request: AnalyzeRequest) -> QueryPlan:
    """Reject unsupported model restrictions before any upstream API request.

    Structured overrides are authoritative and bypass lexical grounding only
    for the specific field provided. We do not infer synonyms from trial data,
    silently drop filters, or call another LLM to 'verify' the first one.
    """
    if plan.intent == "unsupported":
        return plan

    question = request.query
    named = ("condition", "sponsor", "country")
    for field in named:
        value = getattr(plan, field)
        if value is None or getattr(request, field) is not None:
            continue
        grounded = _country_present(question, value) if field == "country" else _contains_phrase(question, value)
        excluded = (_country_excluded(question, value) if field == "country"
                    else _is_excluded(question, value))
        if not grounded or excluded:
            raise QueryError(
                f"The AI plan introduced {field} without explicit question evidence; "
                f"name it in the question or provide the structured {field} filter"
            )

    if request.drugs is None:
        for drug in plan.drugs:
            if not _contains_phrase(question, drug) or _is_excluded(question, drug):
                raise QueryError(
                    "The AI plan introduced drugs without explicit question evidence; "
                    "name each drug or provide a structured drugs filter"
                )

    if plan.start_year is not None and request.start_year is None:
        if not re.search(rf"(?<!\w){plan.start_year}(?!\w)", question):
            raise QueryError(
                "The AI plan introduced start_year without an explicit calendar year; "
                "specify the date or provide the structured start_year filter"
            )

    if (plan.recruiting_only and request.recruiting_only is None
            and not _positive_recruiting_request(question)):
        raise QueryError(
            "The AI plan introduced recruiting_only without an unambiguous "
            "recruiting request; provide recruiting_only explicitly if intended"
        )
    if plan.country is not None:
        return plan.model_copy(update={"country": _canonical_country(plan.country)})
    return plan
