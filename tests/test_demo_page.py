from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from camo.api.main import create_app
from camo.api.rate_limit import InMemoryRateLimiter
from camo.core.settings import Settings
from camo.runtime.session_store import InMemorySessionStore


@pytest.mark.parametrize(
    ("path", "needle"),
    [
        ("/demo", "Two focused demo surfaces"),
        ("/demo/portrait", "Portrait Inspector"),
        ("/demo/chat", "Character Chat"),
    ],
)
def test_demo_pages_render(path: str, needle: str) -> None:
    app = create_app(
        Settings(),
        session_store=InMemorySessionStore(),
        rate_limiter=InMemoryRateLimiter(),
    )

    with TestClient(app) as client:
        response = client.get(path)

    assert response.status_code == 200
    assert needle in response.text
    assert "/demo-assets/demo.css" in response.text
    assert "/demo-assets/demo-common.js" in response.text
