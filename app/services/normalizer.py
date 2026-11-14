"""Convert nested ClinicalTrials.gov protocol records to stable domain objects."""

from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from app.services.terminology import normalized_name


@dataclass(frozen=True, slots=True)
class Intervention:
    name: str
    kind: str
    other_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Study:
    nct_id: str
    title: str
    start_date: str | None
    start_year: int | None
    start_date_type: str | None
    phases: tuple[str, ...]
    status: str | None
    sponsor: str | None
    countries: tuple[str, ...]
    interventions: tuple[Intervention, ...]
    enrollment: int | None

    @property
    def drugs(self) -> tuple[str, ...]:
        return tuple(sorted({x.name for x in self.interventions if x.kind == "DRUG"}))

    @property
    def intervention_types(self) -> tuple[str, ...]:
        return tuple(sorted({x.kind for x in self.interventions if x.kind}))


def _verified_start_date(value: Any) -> tuple[str | None, int | None]:
    """Accept registry ISO dates with year/day precision; reject malformed dates.

    An invalid date cannot safely contribute to a yearly count. Partial
    YYYY and YYYY-MM values are valid, but not precise enough to identify
    whether the study starts later in the current month or year.
    """
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        return None, None
    try:
        pieces = [int(part) for part in value.split("-")]
        date(pieces[0], pieces[1] if len(pieces) >= 2 else 1,
             pieces[2] if len(pieces) == 3 else 1)
    except ValueError:
        return None, None
    return value, pieces[0]


def normalize_study(raw: dict[str, Any]) -> Study:
    protocol = raw.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    nct_id = identification.get("nctId")
    if not isinstance(nct_id, str) or not re.fullmatch(r"NCT\d{8}", nct_id):
        raise ValueError("Study missing a valid NCT ID")

    status = protocol.get("statusModule") or {}
    start = status.get("startDateStruct") or {}
    start_date, start_year = _verified_start_date(start.get("date"))

    design = protocol.get("designModule") or {}
    enrollment_info = design.get("enrollmentInfo") or {}
    enrollment_raw = enrollment_info.get("count")
    enrollment = (enrollment_raw if isinstance(enrollment_raw, int)
                  and not isinstance(enrollment_raw, bool)
                  and enrollment_raw >= 0 else None)
    phases = tuple(dict.fromkeys(str(p) for p in (design.get("phases") or []) if p))

    sponsor_module = protocol.get("sponsorCollaboratorsModule") or {}
    sponsor = (sponsor_module.get("leadSponsor") or {}).get("name")

    locations = (protocol.get("contactsLocationsModule") or {}).get("locations") or []
    countries = tuple(sorted({str(item["country"]).strip() for item in locations
                              if isinstance(item, dict) and item.get("country")}))

    interventions_raw = (protocol.get("armsInterventionsModule") or {}).get("interventions") or []
    interventions_list = []
    for item in interventions_raw:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            continue
        name = item["name"].strip()
        if not name:
            continue
        aliases = item.get("otherNames")
        if not isinstance(aliases, list):
            aliases = []
        # Preserve the displayed registry spellings while removing duplicate
        # names using the same conservative identity rule as the matcher.
        seen_aliases = {normalized_name(name)}
        clean_aliases = []
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                continue
            alias = alias.strip()
            key = normalized_name(alias)
            if key not in seen_aliases:
                seen_aliases.add(key)
                clean_aliases.append(alias)
        interventions_list.append(Intervention(
            name=name, kind=str(item.get("type", "")).upper(),
            other_names=tuple(clean_aliases),
        ))
    interventions = tuple(interventions_list)

    return Study(
        nct_id=nct_id,
        title=str(identification.get("briefTitle", "")),
        start_date=start_date,
        start_year=start_year,
        start_date_type=start.get("type"),
        phases=phases,
        status=status.get("overallStatus"),
        sponsor=sponsor,
        countries=countries,
        interventions=interventions,
        enrollment=enrollment,
    )
