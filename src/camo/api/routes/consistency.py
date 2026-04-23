from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session, get_model_adapter
from camo.api.rate_limit import write_rate_limit
from camo.core.schemas import ConsistencyCheckRequest, ConsistencyCheckResponse
from camo.db.queries.characters import get_character, get_character_by_id
from camo.models.adapter import ModelAdapter
from camo.runtime.anchors import load_active_snapshot, resolve_anchor
from camo.runtime.consistency import run_consistency_check
from camo.runtime.engine import build_fixed_identity_layer, build_stage_layer

router = APIRouter(prefix="/consistency", tags=["consistency"])


@router.post("/check", response_model=ConsistencyCheckResponse, dependencies=[write_rate_limit])
async def consistency_check_endpoint(
    payload: ConsistencyCheckRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    adapter: ModelAdapter = Depends(get_model_adapter),
) -> ConsistencyCheckResponse:
    character = await get_character(session, payload.project_id, payload.character_id)
    if character is None:
        character = await get_character_by_id(session, payload.character_id)
    if character is None or character.project_id != payload.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    anchor_state, _ = await resolve_anchor(
        session,
        project_id=payload.project_id,
        character=character,
        anchor_input=payload.anchor.model_dump(exclude_none=True),
    )
    snapshot = load_active_snapshot(character, anchor_state["resolved_timeline_pos"])
    result = await run_consistency_check(
        model_adapter=adapter,
        character=character,
        anchor_state=anchor_state,
        fixed_identity=build_fixed_identity_layer(character),
        current_stage=build_stage_layer(character, snapshot, anchor_state),
        retrieval_summary={"future_events": []},
        user_input={"speaker": "user", "content": payload.user_input or ""},
        runtime_response={"speaker": character.character_index.get("name", ""), "content": payload.response_text},
        rules_root=request.app.state.rules_root,
    )
    return ConsistencyCheckResponse(
        passed=result["passed"],
        action=result["action"],
        issues=result["issues"],
    )
