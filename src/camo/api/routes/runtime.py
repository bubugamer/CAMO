from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session, get_model_adapter, get_session_store
from camo.api.rate_limit import runtime_turn_rate_limit, write_rate_limit
from camo.core.schemas import (
    RuntimeSessionCreateRequest,
    RuntimeSessionResponse,
    RuntimeSwitchAnchorRequest,
    RuntimeTurnRequest,
    RuntimeTurnResponse,
)
from camo.db.queries.characters import get_character, get_character_by_id
from camo.models.adapter import ModelAdapter
from camo.runtime.anchors import resolve_anchor
from camo.runtime.engine import run_runtime_turn
from camo.runtime.session_store import SessionStore
from camo.tasks.dispatch import TaskQueueUnavailableError, WorkerUnavailableError, enqueue_job

router = APIRouter(prefix="/runtime", tags=["runtime"])
logger = logging.getLogger(__name__)


@router.post(
    "/sessions",
    response_model=RuntimeSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[write_rate_limit],
)
async def create_runtime_session_endpoint(
    payload: RuntimeSessionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    store: SessionStore = Depends(get_session_store),
) -> RuntimeSessionResponse:
    character = await get_character(session, payload.project_id, payload.speaker_target)
    if character is None:
        character = await get_character_by_id(session, payload.speaker_target)
    if character is None or character.project_id != payload.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    anchor_state, _ = await resolve_anchor(
        session,
        project_id=payload.project_id,
        character=character,
        anchor_input=payload.scene.anchor.model_dump(exclude_none=True),
    )
    created_at = datetime.now(timezone.utc)
    session_id = f"sess_{uuid4().hex[:12]}"
    meta = {
        "session_id": session_id,
        "project_id": payload.project_id,
        "speaker_target": character.character_id,
        "participants": payload.participants or [character.character_id],
        "scene": payload.scene.model_dump(mode="json"),
        "anchor": anchor_state,
        "created_at": created_at.isoformat(),
    }
    await store.save_session_meta(session_id, meta)
    return RuntimeSessionResponse(
        session_id=session_id,
        project_id=payload.project_id,
        participants=meta["participants"],
        speaker_target=character.character_id,
        scene=meta["scene"],
        anchor=anchor_state,
        created_at=created_at,
    )


@router.post(
    "/sessions/{session_id}/turns",
    response_model=RuntimeTurnResponse,
    dependencies=[runtime_turn_rate_limit],
)
async def run_runtime_turn_endpoint(
    session_id: str,
    payload: RuntimeTurnRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    adapter: ModelAdapter = Depends(get_model_adapter),
    store: SessionStore = Depends(get_session_store),
) -> RuntimeTurnResponse:
    meta = await store.load_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if payload.speaker_target is not None and payload.speaker_target != meta["speaker_target"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="speaker_target must match the session-bound character",
        )

    character = await get_character_by_id(session, meta["speaker_target"])
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    async def writeback_callback(writeback_payload: dict) -> None:
        try:
            await enqueue_job(
                redis_url=request.app.state.settings.redis_url,
                function_name="run_memory_writeback_task",
                payload=writeback_payload,
            )
        except (TaskQueueUnavailableError, WorkerUnavailableError):
            logger.warning("Runtime memory writeback enqueue failed for session %s", session_id, exc_info=True)

    result = await run_runtime_turn(
        session=session,
        store=store,
        model_adapter=adapter,
        rules_root=request.app.state.rules_root,
        project_id=meta["project_id"],
        session_id=session_id,
        character=character,
        anchor_state=meta["anchor"],
        user_input=payload.user_input.model_dump(),
        participants=payload.participants or meta.get("participants", []),
        recent_history=[item.model_dump() for item in payload.recent_history],
        debug=payload.runtime_options.debug,
        include_reasoning_summary=payload.runtime_options.include_reasoning_summary,
        max_retries=request.app.state.settings.runtime_max_retries,
        writeback_callback=writeback_callback,
    )
    return RuntimeTurnResponse(**result)


@router.post(
    "/sessions/{session_id}/switch-anchor",
    response_model=RuntimeSessionResponse,
    dependencies=[write_rate_limit],
)
async def switch_runtime_anchor_endpoint(
    session_id: str,
    payload: RuntimeSwitchAnchorRequest,
    session: AsyncSession = Depends(get_db_session),
    store: SessionStore = Depends(get_session_store),
) -> RuntimeSessionResponse:
    meta = await store.load_session_meta(session_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    speaker_target = payload.speaker_target or meta["speaker_target"]
    character = await get_character_by_id(session, speaker_target)
    if character is None or character.project_id != meta["project_id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    anchor_state, _ = await resolve_anchor(
        session,
        project_id=meta["project_id"],
        character=character,
        anchor_input=payload.scene.anchor.model_dump(exclude_none=True),
    )
    new_session_id = f"sess_{uuid4().hex[:12]}"
    created_at = datetime.now(timezone.utc)
    new_meta = {
        "session_id": new_session_id,
        "project_id": meta["project_id"],
        "speaker_target": character.character_id,
        "participants": payload.participants or meta.get("participants", []),
        "scene": payload.scene.model_dump(mode="json"),
        "anchor": anchor_state,
        "created_at": created_at.isoformat(),
        "switched_from": session_id,
    }
    await store.save_session_meta(new_session_id, new_meta)
    return RuntimeSessionResponse(
        session_id=new_session_id,
        project_id=meta["project_id"],
        participants=new_meta["participants"],
        speaker_target=character.character_id,
        scene=new_meta["scene"],
        anchor=anchor_state,
        created_at=created_at,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[write_rate_limit],
)
async def delete_runtime_session_endpoint(
    session_id: str,
    store: SessionStore = Depends(get_session_store),
) -> Response:
    await store.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
