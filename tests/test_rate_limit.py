from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from camo.api.deps import get_db_session, get_model_adapter
from camo.api.main import create_app
from camo.api.rate_limit import InMemoryRateLimiter
from camo.core.settings import Settings
from camo.db.models import Character
from camo.runtime.session_store import InMemorySessionStore


async def _fake_db_session():
    yield object()


def _build_app(store: InMemorySessionStore | None = None):
    app = create_app(
        Settings(),
        session_store=store or InMemorySessionStore(),
        rate_limiter=InMemoryRateLimiter(),
    )
    app.dependency_overrides[get_db_session] = _fake_db_session
    app.dependency_overrides[get_model_adapter] = lambda: object()
    return app


def test_read_rate_limit_is_enforced() -> None:
    app = _build_app()

    with TestClient(app) as client:
        last_response = None
        for _ in range(61):
            last_response = client.get("/api/v1/system/health")

    assert last_response is not None
    assert last_response.status_code == 429


def test_write_rate_limit_is_enforced(monkeypatch) -> None:
    app = _build_app()

    async def fake_create_feedback(session, **kwargs):
        return SimpleNamespace(feedback_id="fb_1", created_at=datetime.now(timezone.utc), **kwargs)

    monkeypatch.setattr("camo.api.routes.feedbacks.create_feedback", fake_create_feedback)

    with TestClient(app) as client:
        last_response = None
        for _ in range(21):
            last_response = client.post(
                "/api/v1/feedbacks",
                json={"source": "manual", "target_type": "character_asset", "target_id": "char_demo"},
            )

    assert last_response is not None
    assert last_response.status_code == 429


def test_runtime_turn_rate_limit_is_enforced(monkeypatch) -> None:
    store = InMemorySessionStore()
    asyncio.run(
        store.save_session_meta(
            "sess_demo",
            {
                "session_id": "sess_demo",
                "project_id": "proj_demo",
                "speaker_target": "char_demo",
                "participants": ["char_demo"],
                "anchor": {"resolved_timeline_pos": 1},
            },
        )
    )
    app = _build_app(store)

    async def fake_get_character_by_id(session, character_id):
        return Character(
            character_id=character_id,
            project_id="proj_demo",
            character_index={"name": "岳不群"},
            character_core={},
        )

    async def fake_run_runtime_turn(**kwargs):
        return {
            "session_id": kwargs["session_id"],
            "anchor_state": {"anchor_mode": "source_progress", "resolved_timeline_pos": 1, "display_label": "", "summary": ""},
            "response": {"speaker": "岳不群", "content": "规矩不可乱。", "style_tags": ["formal"]},
            "reasoning_summary": "hidden",
            "triggered_memories": [],
            "applied_rules": [],
            "consistency_check": {"passed": True, "action": "accept", "issues": []},
        }

    monkeypatch.setattr("camo.api.routes.runtime.get_character_by_id", fake_get_character_by_id)
    monkeypatch.setattr("camo.api.routes.runtime.run_runtime_turn", fake_run_runtime_turn)

    with TestClient(app) as client:
        last_response = None
        for _ in range(31):
            last_response = client.post(
                "/api/v1/runtime/sessions/sess_demo/turns",
                json={
                    "user_input": {"speaker": "user", "content": "说下去"},
                    "runtime_options": {"include_reasoning_summary": False, "debug": False},
                },
            )

    assert last_response is not None
    assert last_response.status_code == 429


def test_modeling_submit_rate_limit_is_enforced(monkeypatch) -> None:
    app = _build_app()

    async def fake_get_project(session, project_id):
        return SimpleNamespace(project_id=project_id)

    async def fake_require_active_worker(redis_url: str) -> None:
        return None

    async def fake_enqueue_job(**kwargs):
        return "queued"

    monkeypatch.setattr("camo.api.routes.modeling.get_project", fake_get_project)
    monkeypatch.setattr("camo.api.routes.modeling.require_active_worker", fake_require_active_worker)
    monkeypatch.setattr("camo.api.routes.modeling.enqueue_job", fake_enqueue_job)

    with TestClient(app) as client:
        last_response = None
        for _ in range(6):
            last_response = client.post(
                "/api/v1/projects/proj_demo/modeling",
                json={"source_ids": [], "max_segments_per_chapter": 2},
            )

    assert last_response is not None
    assert last_response.status_code == 429
