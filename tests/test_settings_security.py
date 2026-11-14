"""Configuration boundary tests; no credentials or external calls required."""

import pytest

from app.config import get_settings


@pytest.mark.parametrize("value", ["-1", "0", "nan", "inf", "200", "nonsense"])
def test_invalid_registry_timeouts_fail_at_configuration_boundary(monkeypatch, value):
    monkeypatch.setenv("CLINICALTRIALS_TIMEOUT_SECONDS", value)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="CLINICALTRIALS_TIMEOUT_SECONDS"):
            get_settings()
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize("value", [
    "http://example.com/api/v2", "ftp://clinicaltrials.gov/api/v2",
    "https://user:pass@clinicaltrials.gov/api/v2",
    "https://clinicaltrials.gov/api/v2?token=abc",
])
def test_insecure_registry_endpoint_is_rejected(monkeypatch, value):
    monkeypatch.setenv("CLINICALTRIALS_API_URL", value)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="CLINICALTRIALS_API_URL"):
            get_settings()
    finally:
        get_settings.cache_clear()


def test_loopback_http_allowed_for_controlled_local_integration(monkeypatch):
    monkeypatch.setenv("CLINICALTRIALS_API_URL", "http://127.0.0.1:9999/api/v2")
    get_settings.cache_clear()
    try:
        assert get_settings().clinicaltrials_api_url == "http://127.0.0.1:9999/api/v2"
    finally:
        get_settings.cache_clear()
