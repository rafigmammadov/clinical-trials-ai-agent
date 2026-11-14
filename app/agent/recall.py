"""Conservative detection of explicitly requested filters missing from a query plan.

The extractor recognizes *high-confidence* textual forms only. It is not an
NER model, ontology, or a complete natural-language parser. An unsupported or
omitted recognized constraint fails closed before ClinicalTrials.gov retrieval;
we never silently fill in the model plan with guessed search terms.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agent.grounding import (
    _canonical_country, _country_excluded, _is_excluded, _words,
)
from app.errors import QueryError
from app.schemas.api import AnalyzeRequest, QueryPlan


@dataclass(frozen=True)
class Requirement:
    field: str
    value: str | int | bool | None


# An intentionally bounded, visible lexicon. A country not in this list can
# still be supplied as a structured field; no claim of exhaustive geography.
COUNTRIES = (
    "United States", "United Kingdom", "Canada", "Australia", "India",
    "China", "Japan", "South Korea", "Germany", "France", "Italy", "Spain",
    "Brazil", "Mexico", "Argentina", "Chile", "Colombia", "Peru",
    "New Zealand", "Singapore", "Thailand", "Vietnam", "Indonesia",
    "Philippines", "Pakistan", "Bangladesh", "Azerbaijan", "Turkey",
    "Russia", "Ukraine", "Poland", "Netherlands", "Belgium", "Switzerland",
    "Austria", "Sweden", "Norway", "Denmark", "Finland", "Portugal",
    "Greece", "Ireland", "Israel", "Saudi Arabia", "United Arab Emirates",
    "Egypt", "South Africa", "Kenya", "Nigeria", "Ghana", "Romania",
    "Hungary", "Czech Republic", "Taiwan", "Hong Kong", "Malaysia",
    "Morocco", "Iran", "Iraq", "Jordan", "Lebanon",
)
COUNTRY_ALIASES = {
    "USA": "United States", "U.S.A.": "United States", "US": "United States",
    "U.S.": "United States", "UK": "United Kingdom", "U.K.": "United Kingdom",
}

_STOP_WORDS = {
    "how", "many", "show", "count", "the", "of", "for", "with", "about",
    "in", "on", "and", "a", "an", "by", "all", "which", "what", "are",
    "distribution", "phase", "phases", "trial", "trials", "study", "studies",
    "clinical", "from", "among", "since", "versus", "vs", "comparing",
    "compare", "between", "type", "types", "related", "involving",
    "network", "recruiting", "currently", "active", "ongoing", "yearly",
    "annual", "like", "group", "groups", "data", "over",
}
_COMMON_CONDITIONS = (
    "melanoma", "diabetes", "asthma", "psoriasis", "epilepsy", "obesity",
    "hypertension", "alzheimer's", "parkinson's", "cystic fibrosis",
    "covid-19", "hiv", "tuberculosis", "endometriosis", "arthritis",
)
_CONDITION_PATTERN = re.compile(
    r"\b(?P<term>(?:[\w’'–-]+\s+){0,3}(?:disease|syndrome|cancer)"
    r"(?:\s+type\s+[A-Za-z0-9]+)?)\b", re.IGNORECASE,
)
_EXPLICIT_SPONSOR = re.compile(
    r"\b(?:sponsored\s+by|lead\s+sponsor\s*(?:is|:)?|sponsor\s*[:=])\s*"
    r"(?P<name>[A-Za-z0-9][\w\s&.,'-]{0,120}?)"
    r"(?=\s+(?:in|since|from|through|until|for|with|during|before|after|"
    r"among|where|that|which)\b|[;?!]|$)", re.IGNORECASE,
)
_EXPLICIT_YEAR = r"(?<!\w)((?:19|20)\d{2})(?!\w)"


def _term(text: str) -> str:
    value = text.strip(" \t\r\n,.;:?!")
    tokens = value.split()
    while tokens and tokens[0].casefold() in _STOP_WORDS:
        tokens.pop(0)
    return " ".join(tokens)


def _unique(requirements: list[Requirement]) -> list[Requirement]:
    seen: set[tuple[str, str]] = set()
    result = []
    for item in requirements:
        key = (item.field, _words(str(item.value)))
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _condition_requirements(question: str) -> list[Requirement]:
    result = []
    for match in _CONDITION_PATTERN.finditer(question):
        value = _term(match.group("term"))
        if value and not _is_excluded(question, value):
            result.append(Requirement("condition", value))
    # Terms without a disease/cancer/syndrome suffix are explicitly supported
    # only when they appear as whole words in clinical-study questions.
    normalized = _words(question)
    for name in _COMMON_CONDITIONS:
        phrase = _words(name)
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", normalized):
            if not _is_excluded(question, name) and not re.search(
                rf"\bnon[\s-]+{re.escape(name)}\b", question, re.I
            ):
                result.append(Requirement("condition", name))
    return _unique(result)


def _country_requirements(question: str) -> list[Requirement]:
    found = []
    # Preposition-anchored country mentions and adjectival 'Canada trials'.
    # Explicit names only; never infer geography from institution or city.
    all_terms = [(name, name) for name in COUNTRIES] + list(COUNTRY_ALIASES.items())
    normalized = _words(question)
    for phrase, country in all_terms:
        token = re.escape(_words(phrase))
        if not token:
            continue
        preceded = re.search(
            rf"\b(?:in|within|across|from|within|at|inside)\s+(?:the\s+)?{token}\b",
            normalized,
        )
        modifier = re.search(
            rf"\b{token}\s+(?:clinical\s+)?(?:trials|studies|sites|locations)\b",
            normalized,
        )
        # Country-to-country comparisons are unsupported by the scalar country
        # field; recognize both entities and reject a one-country model plan.
        comparative = re.search(
            rf"\b{token}\s+(?:vs|versus)\b|\b(?:vs|versus)\s+{token}\b",
            normalized,
        )
        if not (preceded or modifier or comparative):
            continue
        # 'Show us trials' is not a United States query. U.S./US as a
        # geographical modifier requires uppercase in the original text.
        if _words(phrase) in {"us", "u s"} and not re.search(
            r"(?<!\w)U(?:\.)?S\.?(?!\w)", question
        ):
            continue
        if not _country_excluded(question, phrase):
            found.append(Requirement("country", _canonical_country(country)))
    # Also recognize a second named country in "in Canada and Germany".
    # Never treat arbitrary "and COUNTRY" as a location without at least one
    # independently recognized country in the same question.
    if found:
        for phrase, country in all_terms:
            token = re.escape(_words(phrase))
            if re.search(rf"\b(?:and|or|versus|vs)\s+{token}\b", normalized):
                if _words(phrase) in {"us", "u s"} and not re.search(
                    r"(?<!\w)U(?:\.)?S\.?(?!\w)", question
                ):
                    continue
                if not _country_excluded(question, phrase):
                    found.append(Requirement("country", _canonical_country(country)))
    return _unique(found)


def _drug_requirements(question: str, intent: str) -> list[Requirement]:
    results = []
    # The purpose-specific keyword avoids guessing whether a free noun phrase
    # is a treatment, a condition, or a study characteristic.
    for match in re.finditer(
        r"\b(?:drug|medication)\s+(?:named\s+)?(?P<name>[A-Za-z][\w-]+)"
        r"(?=\s+(?:trials?|studies|phase|phases|for|in|since)\b|[;?.,!]|$)",
        question, re.I,
    ):
        drug = match.group("name")
        if drug.casefold() not in _STOP_WORDS and not _is_excluded(question, drug):
            results.append(Requirement("drugs", drug))

    if intent == "drug_comparison" and re.search(r"\bcompar(?:e|ing|ison)\b", question, re.I):
        for match in re.finditer(
            r"\b(?P<left>[A-Za-z][\w-]+)\s+(?:vs\.?|versus|and)\s+"
            r"(?P<right>[A-Za-z][\w-]+)\b", question, re.I,
        ):
            left, right = match.group("left"), match.group("right")
            if left.casefold() in _STOP_WORDS or right.casefold() in _STOP_WORDS:
                continue
            if not _is_excluded(question, left) and not _is_excluded(question, right):
                results.extend((Requirement("drugs", left), Requirement("drugs", right)))
    return _unique(results)


def _year_requirements(question: str) -> tuple[list[Requirement], bool]:
    """Return supported year boundaries and whether 'since' is open ended."""
    requirements = []
    # 2018 through 2024, between 2018 and 2024, from 2018 to 2024.
    spans = (
        rf"\bbetween\s+{_EXPLICIT_YEAR}\s+and\s+{_EXPLICIT_YEAR}\b",
        rf"\bfrom\s+{_EXPLICIT_YEAR}\s+(?:to|through|until)\s+{_EXPLICIT_YEAR}\b",
        rf"\b{_EXPLICIT_YEAR}\s*(?:-|–|—|to|through)\s*{_EXPLICIT_YEAR}\b",
    )
    has_range = False
    for pattern in spans:
        match = re.search(pattern, question, re.I)
        if match:
            start, end = map(int, match.groups())
            requirements.extend((Requirement("start_year", start), Requirement("end_year", end)))
            has_range = True
            break
    if not has_range:
        start = re.search(
            rf"\b(?:since|from|starting\s+(?:in|from)|beginning\s+(?:in|from))\s+{_EXPLICIT_YEAR}",
            question, re.I,
        )
        if start:
            requirements.append(Requirement("start_year", int(start.group(1))))
        end = re.search(rf"\b(?:through|until|ending\s+in|up\s+to)\s+{_EXPLICIT_YEAR}", question, re.I)
        if end:
            requirements.append(Requirement("end_year", int(end.group(1))))
        exact = re.search(
            rf"\b(?:trials?|studies)\s+(?:that\s+)?(?:started|began|starting)\s+in\s+{_EXPLICIT_YEAR}",
            question, re.I,
        )
        if exact:
            year = int(exact.group(1))
            requirements.extend((Requirement("start_year", year), Requirement("end_year", year)))
    since = re.search(rf"\bsince\s+{_EXPLICIT_YEAR}", question, re.I)
    open_ended = bool(since and not has_range and not any(
        item.field == "end_year" for item in requirements
    ))
    return _unique(requirements), open_ended


def _recruiting_requirements(question: str) -> list[Requirement]:
    # The word 'recruiting' in a phrase describing *status as a dimension*
    # does not imply a RECRUITING-only study restriction.
    positive = bool(re.search(
        r"\b(?:recruiting|actively\s+enrolling|currently\s+enrolling|"
        r"open\s+for\s+enrollment)\s+(?:(?!status\b|distribution\b)"
        r"[\w-]+\s+){0,5}(?:trials|studies)\b|"
        r"\b(?:trials|studies)\s+(?:that\s+are\s+|which\s+are\s+|"
        r"currently\s+)?recruiting\b|"
        r"\b(?:trials|studies)\s+(?:that\s+are\s+)?(?:now|currently)\s+enrolling\b",
        question, re.I,
    ))
    if re.search(
        r"\b(?:not\s+(?:currently\s+)?recruiting|non[\s-]*recruiting|"
        r"no\s+longer\s+recruiting|without\s+recruiting|"
        r"excluding\s+recruiting)\b", question, re.I,
    ):
        return []
    return [Requirement("recruiting_only", True)] if positive else []


def extract_question_requirements(question: str, intent: str) -> tuple[list[Requirement], bool]:
    """Extract only explicitly marked constraints, never silently infer synonyms."""
    years, open_ended = _year_requirements(question)
    requirements = (
        years + _condition_requirements(question) + _country_requirements(question)
        + _drug_requirements(question, intent) + _recruiting_requirements(question)
    )
    sponsors = list(_EXPLICIT_SPONSOR.finditer(question))
    for match in sponsors:
        name = _term(match.group("name"))
        if name and not _is_excluded(question, name):
            requirements.append(Requirement("sponsor", name))
    return _unique(requirements), open_ended


def _unsupported_constraints(question: str) -> tuple[str, ...]:
    """Recognize exclusions and ambiguous relative/exclusive date constraints.

    Dropping these would turn an explicit constraint into an unrestricted
    query, which is a silent correctness error.
    """
    found = []
    normalized = _words(question)
    if re.search(
        r"\b(?:last|past|previous)\s+(?:\d+|one|two|three|four|five|ten)\s+years?\b|"
        r"\b(?:this|last|previous|current)\s+year\b|"
        r"\b(?:after|before|prior\s+to)\s+(?:19|20)\d{2}\b",
        question, re.I,
    ):
        found.append("calendar_year_semantics")
    if re.search(
        r"\b(?:not|non|no\s+longer)\s+recruiting\b|"
        r"\b(?:no\s+recruiting|without\s+recruiting|"
        r"excluding\s+recruiting)\b", normalized,
    ):
        found.append("recruiting_only")
    for phrase in list(COUNTRIES) + list(COUNTRY_ALIASES):
        value = re.escape(_words(phrase))
        if not value:
            continue
        if re.search(
            rf"\b(?:not\s+in|outside|excluding|except|other\s+than|"
            rf"without\s+sites\s+in)\s+(?:the\s+)?{value}\b",
            normalized,
        ):
            found.append("country")
            break
    for name in _COMMON_CONDITIONS:
        term = re.escape(_words(name))
        if re.search(
            rf"\b(?:without|excluding|except|not\s+including)\s+{term}\b",
            normalized,
        ):
            found.append("condition")
            break
    for match in _CONDITION_PATTERN.finditer(question):
        name = _term(match.group("term"))
        if _is_excluded(question, name):
            found.append("condition")
            break
    if re.search(r"\b(?:without|excluding|except)\s+(?:drug|medication)\s+\w+", question, re.I):
        found.append("drugs")
    return tuple(dict.fromkeys(found))


def missing_question_filters(plan: QueryPlan, request: AnalyzeRequest) -> tuple[str, ...]:
    """Find missed or wrongly narrowed explicitly stated user constraints."""
    required, open_ended_since = extract_question_requirements(request.query, plan.intent)
    issues = []
    grouped: dict[str, list[Requirement]] = {}
    for req in required:
        grouped.setdefault(req.field, []).append(req)
    for field, group in grouped.items():
        if getattr(request, field) is not None:
            continue  # Explicit structured request overrides are authoritative.
        value = getattr(plan, field)
        if field == "drugs":
            if any(_words(str(req.value)) not in {_words(drug) for drug in value} for req in group):
                issues.append(field)
        elif len(group) > 1:
            # Current contract has one country/condition/year boundary. Multiple
            # conflicting requirements cannot be represented as one scalar.
            if len({_words(str(req.value)) for req in group}) > 1:
                issues.append(field)
        elif field == "country":
            if value is None or _words(_canonical_country(value)) != _words(group[0].value):
                issues.append(field)
        elif isinstance(group[0].value, str):
            if value is None or _words(value) != _words(group[0].value):
                issues.append(field)
        elif value != group[0].value:
            issues.append(field)
    if open_ended_since and request.end_year is None and plan.end_year is not None:
        issues.append("end_year")
    return tuple(dict.fromkeys(issues))


def validate_plan_recall(plan: QueryPlan, request: AnalyzeRequest) -> QueryPlan:
    """Fail closed on high-confidence omissions before any upstream request."""
    unsupported = _unsupported_constraints(request.query)
    if unsupported:
        raise QueryError(
            "The requested constraint cannot be represented unambiguously "
            "by supported filters: " + ", ".join(unsupported)
        )
    missing = missing_question_filters(plan, request)
    if missing:
        raise QueryError(
            "The AI plan omitted or changed explicitly requested filters: "
            + ", ".join(missing)
            + "; restate the request or supply typed structured overrides"
        )
    return plan
