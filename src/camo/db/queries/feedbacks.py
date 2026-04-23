from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Feedback


async def create_feedback(
    session: AsyncSession,
    *,
    source: str,
    target_type: str,
    target_id: str,
    rating: str | None = None,
    reason: str | None = None,
    linked_assets: list[str] | None = None,
    suggested_action: str | None = None,
) -> Feedback:
    feedback = Feedback(
        feedback_id=f"fb_{uuid4().hex[:12]}",
        source=source,
        target_type=target_type,
        target_id=target_id,
        rating=rating,
        reason=reason,
        linked_assets=linked_assets or [],
        suggested_action=suggested_action,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return feedback


async def list_feedbacks(
    session: AsyncSession,
    *,
    target_id: str | None = None,
) -> list[Feedback]:
    stmt = select(Feedback).order_by(Feedback.created_at.desc())
    if target_id is not None:
        stmt = stmt.where(Feedback.target_id == target_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())
