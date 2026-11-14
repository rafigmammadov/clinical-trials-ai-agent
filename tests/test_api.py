from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_capabilities_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert "sponsor_drug_network" in response.json()["supported_intents"]


def test_invalid_request_is_422():
    with TestClient(app) as client:
        response = client.post("/api/v1/analyze", json={"query": "Hi"})
    assert response.status_code == 422


def test_complete_http_analysis_with_mock_registry(monkeypatch):
    """End-to-end request flow without network or LLM API credentials."""
    from app.config import get_settings
    from app.services.clinicaltrials import SearchResult
    from app.services.normalizer import normalize_study
    from tests.conftest import raw_study

    class RegistryStub:
        async def search(self, plan, *, max_studies, drug=None):
            assert plan.condition == "Fabry disease"
            return SearchResult(
                studies=(normalize_study(raw_study("NCT00000001", year=2024)),),
                total_matches=1,
                complete=True,
            )

    monkeypatch.setenv("PLANNER_MODE", "rules")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            app.state.trials = RegistryStub()
            response = client.post("/api/v1/analyze", json={
                "query": "How many trials started each year since 2024?",
                "condition": "Fabry disease", "start_year": 2024,
                "end_year": 2024,
            })
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["meta"]["complete"] is True
        assert payload["meta"]["records_used"] == 1
        assert payload["visualization"]["data"][0]["trial_count"] == 1
        assert payload["visualization"]["data"][0]["citations"][0]["nct_id"] == "NCT00000001"
    finally:
        get_settings.cache_clear()
