from __future__ import annotations

from fastapi.testclient import TestClient

from camo.api.main import create_app
from camo.api.rate_limit import InMemoryRateLimiter
from camo.core.settings import Settings
from camo.runtime.session_store import InMemorySessionStore


def _build_test_app(*, api_key: str | None = None):
    return create_app(
        Settings(api_key=api_key),
        session_store=InMemorySessionStore(),
        rate_limiter=InMemoryRateLimiter(),
    )


def test_health_endpoint_reports_loaded_routing_tasks() -> None:
    app = _build_test_app()

    with TestClient(app) as client:
        response = client.get("/api/v1/system/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "CAMO API",
        "environment": "development",
        "routing_tasks": [
            "aggregation",
            "embedding",
            "extraction",
            "judge",
            "runtime",
        ],
    }


def test_api_key_guard_rejects_missing_key_when_enabled() -> None:
    app = _build_test_app(api_key="secret-key")

    with TestClient(app) as client:
        unauthorized = client.get("/api/v1/system/health")
        authorized = client.get("/api/v1/system/health", headers={"X-API-Key": "secret-key"})

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
