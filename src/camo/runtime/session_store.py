from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Protocol

from redis.asyncio import Redis, from_url as redis_from_url


class SessionStoreUnavailableError(RuntimeError):
    """Raised when the configured session store backend is unavailable."""


class SessionStore(Protocol):
    async def connect(self) -> None: ...

    async def aclose(self) -> None: ...

    async def save_session_meta(self, session_id: str, payload: dict[str, Any]) -> None: ...

    async def load_session_meta(self, session_id: str) -> dict[str, Any] | None: ...

    async def delete_session(self, session_id: str) -> None: ...

    async def load_working_memory(self, session_id: str, *, limit: int | None = None) -> list[dict[str, Any]]: ...

    async def append_working_memory(self, session_id: str, item: dict[str, Any]) -> None: ...

    async def save_job_status(self, job_id: str, payload: dict[str, Any]) -> None: ...

    async def load_job_status(self, job_id: str) -> dict[str, Any] | None: ...

    async def patch_job_status(self, job_id: str, **updates: Any) -> dict[str, Any]: ...


class RedisSessionStore:
    def __init__(
        self,
        *,
        redis_url: str,
        session_ttl_seconds: int,
        job_ttl_seconds: int,
        working_memory_limit: int,
    ) -> None:
        self._redis_url = redis_url
        self._session_ttl_seconds = session_ttl_seconds
        self._job_ttl_seconds = job_ttl_seconds
        self._working_memory_limit = working_memory_limit
        self._redis: Redis | None = None

    async def connect(self) -> None:
        try:
            candidate = redis_from_url(self._redis_url, decode_responses=True)
            await candidate.ping()
        except Exception as exc:  # pragma: no cover - connection failure depends on env
            raise SessionStoreUnavailableError(f"Redis session store unavailable: {exc}") from exc
        self._redis = candidate

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def save_session_meta(self, session_id: str, payload: dict[str, Any]) -> None:
        redis = self._require_redis()
        await redis.set(
            self._session_key(session_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._session_ttl_seconds,
        )

    async def load_session_meta(self, session_id: str) -> dict[str, Any] | None:
        redis = self._require_redis()
        raw = await redis.get(self._session_key(session_id))
        if raw is None:
            return None
        await redis.expire(self._session_key(session_id), self._session_ttl_seconds)
        return json.loads(raw)

    async def delete_session(self, session_id: str) -> None:
        redis = self._require_redis()
        await redis.delete(self._session_key(session_id), self._working_memory_key(session_id))

    async def load_working_memory(self, session_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        redis = self._require_redis()
        resolved_limit = limit or self._working_memory_limit
        raw_items = await redis.lrange(self._working_memory_key(session_id), -resolved_limit, -1)
        await redis.expire(self._working_memory_key(session_id), self._session_ttl_seconds)
        return [json.loads(item) for item in raw_items]

    async def append_working_memory(self, session_id: str, item: dict[str, Any]) -> None:
        redis = self._require_redis()
        key = self._working_memory_key(session_id)
        await redis.rpush(key, json.dumps(item, ensure_ascii=False))
        await redis.ltrim(key, -self._working_memory_limit, -1)
        await redis.expire(key, self._session_ttl_seconds)

    async def save_job_status(self, job_id: str, payload: dict[str, Any]) -> None:
        redis = self._require_redis()
        await redis.set(
            self._job_key(job_id),
            json.dumps(payload, ensure_ascii=False),
            ex=self._job_ttl_seconds,
        )

    async def load_job_status(self, job_id: str) -> dict[str, Any] | None:
        redis = self._require_redis()
        raw = await redis.get(self._job_key(job_id))
        if raw is None:
            return None
        await redis.expire(self._job_key(job_id), self._job_ttl_seconds)
        return json.loads(raw)

    async def patch_job_status(self, job_id: str, **updates: Any) -> dict[str, Any]:
        payload = await self.load_job_status(job_id) or {}
        payload.update(updates)
        await self.save_job_status(job_id, payload)
        return payload

    def _require_redis(self) -> Redis:
        if self._redis is None:
            raise SessionStoreUnavailableError("Redis session store is not connected")
        return self._redis

    @staticmethod
    def _session_key(session_id: str) -> str:
        return f"session:{session_id}:meta"

    @staticmethod
    def _working_memory_key(session_id: str) -> str:
        return f"wm:{session_id}"

    @staticmethod
    def _job_key(job_id: str) -> str:
        return f"job:{job_id}"


@dataclass
class _MemoryBackend:
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    working_memory: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    jobs: dict[str, dict[str, Any]] = field(default_factory=dict)


class InMemorySessionStore:
    def __init__(
        self,
        *,
        session_ttl_seconds: int = 7200,
        job_ttl_seconds: int = 86400,
        working_memory_limit: int = 50,
    ) -> None:
        self._session_ttl_seconds = session_ttl_seconds
        self._job_ttl_seconds = job_ttl_seconds
        self._working_memory_limit = working_memory_limit
        self._backend = _MemoryBackend()

    async def connect(self) -> None:
        return None

    async def aclose(self) -> None:
        return None

    async def save_session_meta(self, session_id: str, payload: dict[str, Any]) -> None:
        self._backend.sessions[session_id] = deepcopy(payload)

    async def load_session_meta(self, session_id: str) -> dict[str, Any] | None:
        payload = self._backend.sessions.get(session_id)
        return deepcopy(payload) if payload is not None else None

    async def delete_session(self, session_id: str) -> None:
        self._backend.sessions.pop(session_id, None)
        self._backend.working_memory.pop(session_id, None)

    async def load_working_memory(self, session_id: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        resolved_limit = limit or self._working_memory_limit
        items = self._backend.working_memory.get(session_id, [])
        return deepcopy(items[-resolved_limit:])

    async def append_working_memory(self, session_id: str, item: dict[str, Any]) -> None:
        bucket = self._backend.working_memory.setdefault(session_id, [])
        bucket.append(deepcopy(item))
        if len(bucket) > self._working_memory_limit:
            del bucket[:-self._working_memory_limit]

    async def save_job_status(self, job_id: str, payload: dict[str, Any]) -> None:
        self._backend.jobs[job_id] = deepcopy(payload)

    async def load_job_status(self, job_id: str) -> dict[str, Any] | None:
        payload = self._backend.jobs.get(job_id)
        return deepcopy(payload) if payload is not None else None

    async def patch_job_status(self, job_id: str, **updates: Any) -> dict[str, Any]:
        payload = await self.load_job_status(job_id) or {}
        payload.update(updates)
        await self.save_job_status(job_id, payload)
        return payload
