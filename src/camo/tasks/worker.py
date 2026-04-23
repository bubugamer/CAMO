from __future__ import annotations

import asyncio
from contextlib import suppress
from os import getpid
from socket import gethostname

from arq.connections import RedisSettings
from redis.asyncio import from_url as redis_from_url

from camo.core.settings import Settings
from camo.db.session import create_engine, create_session_factory
from camo.models import ModelAdapter, build_provider_registry
from camo.models.config import load_model_routing_config
from camo.runtime.session_store import RedisSessionStore
from camo.tasks.dispatch import WORKER_HEARTBEAT_PREFIX
from camo.tasks.modeling import run_project_modeling, write_runtime_memory

WORKER_HEARTBEAT_TTL_SECONDS = 30


async def startup(ctx) -> None:
    settings = Settings()
    routing = load_model_routing_config(settings.model_config_path, env=settings.model_env())
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    model_adapter = ModelAdapter(
        routing,
        providers=build_provider_registry(routing),
    )
    store = RedisSessionStore(
        redis_url=settings.redis_url,
        session_ttl_seconds=settings.session_ttl_seconds,
        job_ttl_seconds=settings.job_ttl_seconds,
        working_memory_limit=settings.working_memory_limit,
    )
    await store.connect()
    heartbeat_redis = redis_from_url(settings.redis_url, decode_responses=True)
    worker_id = f"{gethostname()}:{getpid()}"
    heartbeat_key = f"{WORKER_HEARTBEAT_PREFIX}{worker_id}"
    heartbeat_stop = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _run_worker_heartbeat(
            redis=heartbeat_redis,
            heartbeat_key=heartbeat_key,
            stop_event=heartbeat_stop,
        )
    )
    ctx.update(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        model_adapter=model_adapter,
        store=store,
        heartbeat_redis=heartbeat_redis,
        heartbeat_key=heartbeat_key,
        heartbeat_stop=heartbeat_stop,
        heartbeat_task=heartbeat_task,
    )


async def shutdown(ctx) -> None:
    ctx["heartbeat_stop"].set()
    ctx["heartbeat_task"].cancel()
    with suppress(asyncio.CancelledError):
        await ctx["heartbeat_task"]
    await ctx["heartbeat_redis"].delete(ctx["heartbeat_key"])
    await ctx["heartbeat_redis"].aclose()
    await ctx["model_adapter"].aclose()
    await ctx["store"].aclose()
    await ctx["engine"].dispose()


async def run_modeling_job_task(ctx, payload: dict) -> dict:
    return await run_project_modeling(
        session_factory=ctx["session_factory"],
        model_adapter=ctx["model_adapter"],
        store=ctx["store"],
        job_id=payload["job_id"],
        project_id=payload["project_id"],
        source_ids=payload.get("source_ids"),
        segment_limit=payload.get("segment_limit"),
        max_segments_per_chapter=payload.get("max_segments_per_chapter", 10),
    )


async def run_memory_writeback_task(ctx, payload: dict) -> None:
    await write_runtime_memory(
        session_factory=ctx["session_factory"],
        model_adapter=ctx["model_adapter"],
        payload=payload,
    )


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(Settings().redis_url)
    functions = [run_modeling_job_task, run_memory_writeback_task]
    on_startup = startup
    on_shutdown = shutdown


async def _run_worker_heartbeat(*, redis, heartbeat_key: str, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await redis.set(heartbeat_key, "alive", ex=WORKER_HEARTBEAT_TTL_SECONDS)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=WORKER_HEARTBEAT_TTL_SECONDS / 3)
        except TimeoutError:
            continue
