from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session, get_session_store
from camo.api.rate_limit import modeling_submit_rate_limit, read_rate_limit
from camo.core.schemas import ModelingJobCreateRequest, ModelingJobCreateResponse, ModelingJobStatusResponse
from camo.db.queries.projects import get_project
from camo.runtime.session_store import SessionStore
from camo.tasks.dispatch import (
    TaskQueueUnavailableError,
    WorkerUnavailableError,
    enqueue_job,
    require_active_worker,
)

router = APIRouter(tags=["modeling"])


@router.post(
    "/projects/{project_id}/modeling",
    response_model=ModelingJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[modeling_submit_rate_limit],
)
async def create_modeling_job_endpoint(
    project_id: str,
    payload: ModelingJobCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    store: SessionStore = Depends(get_session_store),
) -> ModelingJobCreateResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    job_id = f"job_{uuid4().hex[:12]}"
    initial_status = {
        "job_id": job_id,
        "project_id": project_id,
        "status": "queued",
        "progress": 0.0,
        "message": "Queued for modeling",
        "stage": "queued",
        "stage_message": "Queued for modeling",
        "processed_sources": 0,
        "processed_characters": 0,
        "character_count": 0,
        "current_source_id": None,
        "current_character_id": None,
        "current_chapter": None,
        "error": None,
    }
    await store.save_job_status(job_id, initial_status)
    enqueue_payload = {
        "job_id": job_id,
        "project_id": project_id,
        "source_ids": payload.source_ids,
        "segment_limit": payload.segment_limit,
        "max_segments_per_chapter": payload.max_segments_per_chapter,
    }
    try:
        await require_active_worker(request.app.state.settings.redis_url)
        await enqueue_job(
            redis_url=request.app.state.settings.redis_url,
            function_name="run_modeling_job_task",
            payload=enqueue_payload,
        )
    except (TaskQueueUnavailableError, WorkerUnavailableError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return ModelingJobCreateResponse(job_id=job_id, project_id=project_id, status="queued")


@router.get(
    "/projects/{project_id}/modeling/{job_id}",
    response_model=ModelingJobStatusResponse,
    dependencies=[read_rate_limit],
)
async def get_modeling_job_status_endpoint(
    project_id: str,
    job_id: str,
    store: SessionStore = Depends(get_session_store),
) -> ModelingJobStatusResponse:
    payload = await store.load_job_status(job_id)
    if payload is None or payload.get("project_id") != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Modeling job not found")
    return ModelingJobStatusResponse(**payload)
