from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from camo.api.routes.modeling import create_modeling_job_endpoint
from camo.api.routes.runtime import run_runtime_turn_endpoint
from camo.core.schemas import ModelingJobCreateRequest, RuntimeOptions, RuntimeTurnRequest, RuntimeUserInput
from camo.runtime.session_store import InMemorySessionStore
from camo.tasks.dispatch import WorkerUnavailableError


def test_runtime_route_rejects_mismatched_speaker_target() -> None:
    store = InMemorySessionStore()

    async def run() -> None:
        await store.connect()
        await store.save_session_meta(
            "sess_demo",
            {
                "session_id": "sess_demo",
                "project_id": "proj_demo",
                "speaker_target": "char_bound",
                "participants": ["char_bound"],
                "anchor": {"resolved_timeline_pos": 1},
            },
        )
        payload = RuntimeTurnRequest(
            speaker_target="char_other",
            user_input=RuntimeUserInput(content="继续说"),
            runtime_options=RuntimeOptions(),
        )
        with pytest.raises(HTTPException) as exc_info:
            await run_runtime_turn_endpoint(
                session_id="sess_demo",
                payload=payload,
                request=SimpleNamespace(app=None),
                session=object(),
                adapter=object(),
                store=store,
            )
        assert exc_info.value.status_code == 400

    asyncio.run(run())


def test_modeling_route_returns_503_when_no_worker_is_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    store = InMemorySessionStore()

    async def fake_get_project(session, project_id):
        return SimpleNamespace(project_id=project_id)

    async def fake_require_active_worker(redis_url: str) -> None:
        raise WorkerUnavailableError("No active worker heartbeat found")

    monkeypatch.setattr("camo.api.routes.modeling.get_project", fake_get_project)
    monkeypatch.setattr("camo.api.routes.modeling.require_active_worker", fake_require_active_worker)

    async def run() -> None:
        await store.connect()
        payload = ModelingJobCreateRequest(max_segments_per_chapter=3)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(redis_url="redis://test"))))
        with pytest.raises(HTTPException) as exc_info:
            await create_modeling_job_endpoint(
                project_id="proj_demo",
                payload=payload,
                request=request,
                session=object(),
                store=store,
            )
        assert exc_info.value.status_code == 503

    asyncio.run(run())
