"""Conservative matching of named DRUG interventions against registry records.

Text search retrieves candidate records. This module verifies membership from
registered intervention names or their explicitly recorded `otherNames`. It
is not an ontology, synonym service, or a claim of pharmacologic equivalence.
"""

from dataclasses import dataclass

from app.services.normalizer import Study
from app.services.terminology import normalized_name


NAME_FIELD = "protocolSection.armsInterventionsModule.interventions[].name"
ALIAS_FIELD = "protocolSection.armsInterventionsModule.interventions[].otherNames[]"


@dataclass(frozen=True, slots=True)
class RegisteredDrugMatch:
    field_path: str
    excerpt: str
    registered_name: str


def find_registered_drug_match(study: Study, term: str) -> RegisteredDrugMatch | None:
    """Find an exact registered DRUG name or alias, never a substring/guess."""
    target = normalized_name(term)
    if not target:
        return None
    for intervention in study.interventions:
        if intervention.kind != "DRUG":
            continue
        if normalized_name(intervention.name) == target:
            return RegisteredDrugMatch(NAME_FIELD, intervention.name, intervention.name)
        for alias in intervention.other_names:
            if normalized_name(alias) == target:
                return RegisteredDrugMatch(ALIAS_FIELD, alias, intervention.name)
    return None
