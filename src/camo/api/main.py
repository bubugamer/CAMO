from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from camo import __version__
from camo.api.routes import (
    characters_router,
    consistency_router,
    demo_router,
    events_router,
    feedbacks_router,
    modeling_router,
    projects_router,
    relationships_router,
    reviews_router,
    runtime_router,
    system_router,
    texts_router,
)
from camo.api.rate_limit import RateLimiter, RedisRateLimiter
from camo.core.settings import Settings, get_settings
from camo.db.queries.llm_logs import persist_llm_log_entry
from camo.db.session import create_engine, create_session_factory
from camo.models import ModelAdapter, build_provider_registry
from camo.models.config import load_model_routing_config
from camo.runtime.session_store import RedisSessionStore, SessionStore


def create_app(
    settings: Settings | None = None,
    *,
    session_store: SessionStore | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = app_settings
        app.state.model_routing = load_model_routing_config(
            app_settings.model_config_path,
            env=app_settings.model_env(),
        )
        app.state.engine = create_engine(app_settings.database_url)
        app.state.session_factory = create_session_factory(app.state.engine)
        app.state.model_adapter = ModelAdapter(
            app.state.model_routing,
            providers=build_provider_registry(app.state.model_routing),
            log_callback=_build_log_callback(app.state.session_factory),
        )
        app.state.session_store = session_store or RedisSessionStore(
            redis_url=app_settings.redis_url,
            session_ttl_seconds=app_settings.session_ttl_seconds,
            job_ttl_seconds=app_settings.job_ttl_seconds,
            working_memory_limit=app_settings.working_memory_limit,
        )
        app.state.rate_limiter = rate_limiter or RedisRateLimiter(
            redis_url=app_settings.redis_url,
        )
        await app.state.session_store.connect()
        await app.state.rate_limiter.connect()
        app_settings.data_root.mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "raw_texts").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "exports").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "rules" / "meta").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "rules" / "setting").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "rules" / "plot").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "rules" / "custom").mkdir(parents=True, exist_ok=True)
        app.state.rules_root = app_settings.data_root / "rules"
        yield
        await app.state.rate_limiter.aclose()
        await app.state.session_store.aclose()
        await app.state.model_adapter.aclose()
        await app.state.engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/demo-assets", StaticFiles(directory=str(static_dir)), name="demo-assets")

    @app.middleware("http")
    async def api_key_guard(request, call_next):
        if (
            app_settings.api_key
            and request.url.path.startswith(app_settings.api_v1_prefix)
            and request.headers.get("X-API-Key") != app_settings.api_key
        ):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)

    app.include_router(demo_router)
    app.include_router(system_router, prefix=app_settings.api_v1_prefix)
    app.include_router(projects_router, prefix=app_settings.api_v1_prefix)
    app.include_router(texts_router, prefix=app_settings.api_v1_prefix)
    app.include_router(characters_router, prefix=app_settings.api_v1_prefix)
    app.include_router(events_router, prefix=app_settings.api_v1_prefix)
    app.include_router(modeling_router, prefix=app_settings.api_v1_prefix)
    app.include_router(relationships_router, prefix=app_settings.api_v1_prefix)
    app.include_router(runtime_router, prefix=app_settings.api_v1_prefix)
    app.include_router(consistency_router, prefix=app_settings.api_v1_prefix)
    app.include_router(reviews_router, prefix=app_settings.api_v1_prefix)
    app.include_router(feedbacks_router, prefix=app_settings.api_v1_prefix)

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _build_log_callback(session_factory):
    async def log_callback(entry) -> None:
        try:
            async with session_factory() as session:
                await persist_llm_log_entry(session, entry)
        except Exception:
            return None

    return log_callback


app = create_app()
