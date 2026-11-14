import pytest

from app.services.normalizer import normalize_study
from tests.conftest import raw_study


def test_normalization_extracts_study_fields():
    study = normalize_study(raw_study(phases=["PHASE1", "PHASE2"],
                                      drugs=["Drug A", "Drug B"],
                                      countries=["Canada", "Canada", "Germany"]))
    assert study.nct_id == "NCT00000001"
    assert study.start_year == 2024
    assert study.phases == ("PHASE1", "PHASE2")
    assert study.countries == ("Canada", "Germany")
    assert study.drugs == ("Drug A", "Drug B")
    assert study.enrollment == 150


def test_missing_dates_allowed():
    study = normalize_study(raw_study(year=None))
    assert study.start_date is None
    assert study.start_year is None


def test_missing_nct_rejected():
    with pytest.raises(ValueError):
        normalize_study({"protocolSection": {"identificationModule": {}}})
