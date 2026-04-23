from __future__ import annotations

import asyncio

import pytest

from camo.runtime.session_store import InMemorySessionStore, RedisSessionStore, SessionStoreUnavailableError


def test_redis_session_store_raises_when_backend_is_unavailable() -> None:
    store = RedisSessionStore(
        redis_url="redis://127.0.0.1:6399/0",
        session_ttl_seconds=60,
        job_ttl_seconds=60,
        working_memory_limit=2,
    )

    async def run() -> None:
        with pytest.raises(SessionStoreUnavailableError):
            await store.connect()

    asyncio.run(run())


def test_in_memory_session_store_is_explicit_test_double() -> None:
    store = InMemorySessionStore(
        session_ttl_seconds=60,
        job_ttl_seconds=60,
        working_memory_limit=2,
    )

    async def run() -> None:
        await store.connect()
        await store.save_session_meta("sess_demo", {"session_id": "sess_demo", "project_id": "proj_demo"})
        await store.append_working_memory("sess_demo", {"speaker": "user", "content": "A"})
        await store.append_working_memory("sess_demo", {"speaker": "assistant", "content": "B"})
        await store.append_working_memory("sess_demo", {"speaker": "user", "content": "C"})
        loaded = await store.load_session_meta("sess_demo")
        wm = await store.load_working_memory("sess_demo")
        assert loaded["project_id"] == "proj_demo"
        assert [item["content"] for item in wm] == ["B", "C"]

    asyncio.run(run())
