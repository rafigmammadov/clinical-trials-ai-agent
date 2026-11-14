"""Independent citation-to-source consistency checks for deterministic charts.

This validates excerpts against the normalized studies fetched in this request.
It is NOT a cryptographic proof of the remote registry's authenticity.
"""
from __future__ import annotations

from app.schemas.api import VisualizationSpec
from app.services.normalizer import Study

PREFIX = "protocolSection."
SOURCE_VALUES = {
    PREFIX + "identificationModule.nctId": lambda s: {s.nct_id},
    PREFIX + "statusModule.startDateStruct.date": lambda s: {s.start_date},
    PREFIX + "designModule.phases": lambda s: set(s.phases),
    PREFIX + "statusModule.overallStatus": lambda s: {s.status},
    PREFIX + "sponsorCollaboratorsModule.leadSponsor.name": lambda s: {s.sponsor},
    PREFIX + "contactsLocationsModule.locations[].country": lambda s: set(s.countries),
    PREFIX + "armsInterventionsModule.interventions[].name": lambda s: {
        i.name for i in s.interventions if i.kind == "DRUG"
    },
    PREFIX + "armsInterventionsModule.interventions[].otherNames[]": lambda s: {
        alias for i in s.interventions if i.kind == "DRUG" for alias in i.other_names
    },
    PREFIX + "armsInterventionsModule.interventions[].type": lambda s: {
        i.kind for i in s.interventions
    },
    PREFIX + "designModule.enrollmentInfo.count": lambda s: {s.enrollment},
}


def _assert_field(study: Study, path: str, excerpt: str) -> None:
    getter = SOURCE_VALUES.get(path)
    if getter is None or excerpt not in {str(x) for x in getter(study) if x is not None}:
        raise ValueError("Chart citation value is not supported by its source study")


def verify_chart_evidence(chart: VisualizationSpec, studies: list[Study]) -> None:
    """Fail closed when chart evidence does not match fetched NCT records."""
    known = {study.nct_id: study for study in studies}
    rows = (chart.data["nodes"] + chart.data["edges"]
            if chart.type == "network_graph" else chart.data)
    for row in rows:
        cited: set[str] = set()
        for ref in row.get("citations", []):
            nct_id = ref.get("nct_id")
            study = known.get(nct_id)
            if study is None or nct_id in cited:
                raise ValueError("Chart citation has unknown or repeated NCT ID")
            cited.add(nct_id)
            if ref.get("url") != f"https://clinicaltrials.gov/study/{nct_id}":
                raise ValueError("Chart citation has a noncanonical NCT URL")
            _assert_field(study, ref.get("field_path"), str(ref.get("excerpt")))
            for qualifier in ("related", "matched_drug"):
                path, excerpt = (ref.get(f"{qualifier}_field_path"),
                                 ref.get(f"{qualifier}_excerpt"))
                if (path is None) != (excerpt is None):
                    raise ValueError("Chart citation has incomplete paired evidence")
                if path is not None:
                    _assert_field(study, path, str(excerpt))
            if (ref.get("evidence_scope") == "record_identity_only"
                    and ref.get("field_path") != PREFIX + "identificationModule.nctId"):
                raise ValueError("Record-identity-only evidence has the wrong source field")
        if row.get("citations_complete") and len(cited) != row.get("citation_count"):
            raise ValueError("Complete chart citations do not match the stated study count")
        if len(cited) > row.get("citation_count", 0):
            raise ValueError("Chart has more source citations than contributing records")
