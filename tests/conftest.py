"""ClinicalTrials.gov-shaped fixtures, fully offline and deterministic."""

from typing import Any
import pytest

from app.services.normalizer import normalize_study


def raw_study(
    nct: str = "NCT00000001", *, year: int | None = 2024,
    phases: list[str] | None = None,
    drugs: list[str] | None = None,
    sponsor: str = "Acme Research", countries: list[str] | None = None,
    status: str = "RECRUITING", enrollment: int = 150,
) -> dict[str, Any]:
    return {
        "protocolSection": {
            "identificationModule": {"nctId": nct, "briefTitle": f"Study {nct}"},
            "statusModule": {
                "overallStatus": status,
                "startDateStruct": ({"date": f"{year}-03-01", "type": "ACTUAL"} if year else {}),
            },
            "designModule": {
                "phases": phases if phases is not None else ["PHASE2"],
                "enrollmentInfo": {"count": enrollment, "type": "ACTUAL"},
            },
            "sponsorCollaboratorsModule": {"leadSponsor": {"name": sponsor}},
            "contactsLocationsModule": {"locations": [
                {"country": c} for c in (countries if countries is not None else ["United States"])
            ]},
            "armsInterventionsModule": {"interventions": [
                {"name": d, "type": "DRUG"} for d in (drugs if drugs is not None else ["Drug A"])
            ]},
        }
    }


@pytest.fixture
def studies():
    return [
        normalize_study(raw_study("NCT00000001", year=2023, phases=["PHASE1", "PHASE2"],
                                  drugs=["Drug A", "Drug B"], countries=["United States", "Canada"])),
        normalize_study(raw_study("NCT00000002", year=2024, phases=["PHASE2"],
                                  drugs=["Drug A"], sponsor="Other Research")),
        normalize_study(raw_study("NCT00000003", year=2024, phases=["PHASE3"],
                                  drugs=["Drug B", "Drug C"])),
    ]
