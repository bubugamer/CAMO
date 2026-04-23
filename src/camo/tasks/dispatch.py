from __future__ import annotations

from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import from_url as redis_from_url

WORKER_HEARTBEAT_PREFIX = "worker:heartbeat:"


class TaskQueueUnavailableError(RuntimeError):
    """Raised when the task queue cannot accept jobs."""


class WorkerUnavailableError(RuntimeError):
    """Raised when no active worker heartbeat is available."""


async def enqueue_job(
    *,
    redis_url: str,
    function_name: str,
    payload: dict[str, Any],
) -> str:
    try:
        pool = await create_pool(RedisSettings.from_dsn(redis_url))
    except Exception as exc:  # pragma: no cover - depends on queue backend
        raise TaskQueueUnavailableError(f"Task queue unavailable: {exc}") from exc

    try:
        await pool.enqueue_job(function_name, payload)
    except Exception as exc:  # pragma: no cover - depends on queue backend
        raise TaskQueueUnavailableError(f"Failed to enqueue task '{function_name}': {exc}") from exc
    finally:
        await pool.aclose()

    return "queued"


async def require_active_worker(redis_url: str) -> None:
    if not await has_active_worker(redis_url):
        raise WorkerUnavailableError("No active worker heartbeat found")


async def has_active_worker(redis_url: str) -> bool:
    redis = redis_from_url(redis_url, decode_responses=True)
    try:
        async for _ in redis.scan_iter(match=f"{WORKER_HEARTBEAT_PREFIX}*", count=1):
            return True
        return False
    except Exception as exc:  # pragma: no cover - depends on redis availability
        raise TaskQueueUnavailableError(f"Task queue unavailable: {exc}") from exc
    finally:
        await redis.aclose()
