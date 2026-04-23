from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import write_rate_limit
from camo.core.schemas import FeedbackCreateRequest, FeedbackResponse
from camo.db.queries.feedbacks import create_feedback

router = APIRouter(tags=["feedbacks"])


@router.post("/feedbacks", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED, dependencies=[write_rate_limit])
async def create_feedback_endpoint(
    payload: FeedbackCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> FeedbackResponse:
    feedback = await create_feedback(
        session,
        source=payload.source,
        target_type=payload.target_type,
        target_id=payload.target_id,
        rating=payload.rating,
        reason=payload.reason,
        linked_assets=payload.linked_assets,
        suggested_action=payload.suggested_action,
    )
    return FeedbackResponse(
        feedback_id=feedback.feedback_id,
        source=feedback.source,
        target_type=feedback.target_type,
        target_id=feedback.target_id,
        rating=feedback.rating,
        reason=feedback.reason,
        linked_assets=feedback.linked_assets,
        suggested_action=feedback.suggested_action,
        created_at=feedback.created_at,
    )
