from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from camo.api.deps import get_model_adapter
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.schemas import HealthResponse, ModelCheckRequest, ModelCheckResponse
from camo.models.adapter import ModelAdapter, ProviderConfigurationError

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthResponse, dependencies=[read_rate_limit])
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    routing_config = request.app.state.model_routing
    return HealthResponse(
        status="ok",
        app_name=settings.app_name,
        environment=settings.environment,
        routing_tasks=routing_config.list_tasks(),
    )


@router.post("/model-check", response_model=ModelCheckResponse, dependencies=[write_rate_limit])
async def model_check(
    payload: ModelCheckRequest,
    adapter: ModelAdapter = Depends(get_model_adapter),
) -> ModelCheckResponse:
    try:
        result = await adapter.complete(
            messages=[{"role": "user", "content": payload.prompt}],
            task=payload.task,
        )
    except ProviderConfigurationError as exc:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return ModelCheckResponse(
        task=payload.task,
        model=result.model,
        content=result.content,
        structured=result.structured,
        usage=result.usage,
        latency_ms=result.latency_ms,
    )
