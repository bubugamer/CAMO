from __future__ import annotations

from time import time
from typing import Protocol

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis, from_url as redis_from_url


class RateLimiter(Protocol):
    async def connect(self) -> None: ...

    async def aclose(self) -> None: ...

    async def check(self, request: Request, *, category: str, limit: int) -> None: ...


class RateLimiterUnavailableError(RuntimeError):
    """Raised when the configured rate limiter backend is unavailable."""


class RedisRateLimiter:
    def __init__(self, *, redis_url: str, window_seconds: int = 60) -> None:
        self._redis_url = redis_url
        self._window_seconds = window_seconds
        self._redis: Redis | None = None

    async def connect(self) -> None:
        try:
            candidate = redis_from_url(self._redis_url, decode_responses=True)
            await candidate.ping()
        except Exception as exc:  # pragma: no cover - depends on env
            raise RateLimiterUnavailableError(f"Redis rate limiter unavailable: {exc}") from exc
        self._redis = candidate

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def check(self, request: Request, *, category: str, limit: int) -> None:
        redis = self._require_redis()
        client_host = request.client.host if request.client is not None else "unknown"
        window_bucket = int(time() // self._window_seconds)
        key = f"rate_limit:{category}:{client_host}:{window_bucket}"
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, self._window_seconds * 2)
        if current > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )

    def _require_redis(self) -> Redis:
        if self._redis is None:
            raise RateLimiterUnavailableError("Redis rate limiter is not connected")
        return self._redis


class InMemoryRateLimiter:
    def __init__(self, *, window_seconds: int = 60) -> None:
        self._window_seconds = window_seconds
        self._buckets: dict[str, tuple[int, int]] = {}

    async def connect(self) -> None:
        return None

    async def aclose(self) -> None:
        self._buckets.clear()

    async def check(self, request: Request, *, category: str, limit: int) -> None:
        client_host = request.client.host if request.client is not None else "unknown"
        window_bucket = int(time() // self._window_seconds)
        key = f"{category}:{client_host}"
        current_bucket, count = self._buckets.get(key, (window_bucket, 0))
        if current_bucket != window_bucket:
            current_bucket, count = window_bucket, 0
        count += 1
        self._buckets[key] = (current_bucket, count)
        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )


def _make_dependency(category: str, limit: int):
    async def dependency(request: Request) -> None:
        limiter: RateLimiter = request.app.state.rate_limiter
        await limiter.check(request, category=category, limit=limit)

    return Depends(dependency)


read_rate_limit = _make_dependency("read", 60)
write_rate_limit = _make_dependency("write", 20)
runtime_turn_rate_limit = _make_dependency("runtime_turn", 30)
modeling_submit_rate_limit = _make_dependency("modeling_submit", 5)
