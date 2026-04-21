from __future__ import annotations

from fastapi.testclient import TestClient

from camo.api.main import create_app
from camo.core.settings import Settings


def test_health_endpoint_reports_loaded_routing_tasks() -> None:
    app = create_app(Settings())

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
