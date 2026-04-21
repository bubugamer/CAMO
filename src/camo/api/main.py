from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from camo import __version__
from camo.api.routes import characters_router, demo_router, projects_router, system_router, texts_router
from camo.core.settings import Settings, get_settings
from camo.db.queries.llm_logs import persist_llm_log_entry
from camo.db.session import create_engine, create_session_factory
from camo.models import ModelAdapter, build_provider_registry
from camo.models.config import load_model_routing_config


def create_app(settings: Settings | None = None) -> FastAPI:
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
        app_settings.data_root.mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "raw_texts").mkdir(parents=True, exist_ok=True)
        (app_settings.data_root / "exports").mkdir(parents=True, exist_ok=True)
        yield
        await app.state.model_adapter.aclose()
        await app.state.engine.dispose()

    app = FastAPI(
        title=app_settings.app_name,
        version=__version__,
        lifespan=lifespan,
    )
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/demo-assets", StaticFiles(directory=str(static_dir)), name="demo-assets")
    app.include_router(demo_router)
    app.include_router(system_router, prefix=app_settings.api_v1_prefix)
    app.include_router(projects_router, prefix=app_settings.api_v1_prefix)
    app.include_router(texts_router, prefix=app_settings.api_v1_prefix)
    app.include_router(characters_router, prefix=app_settings.api_v1_prefix)

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
