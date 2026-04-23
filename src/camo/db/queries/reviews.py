from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Review


async def create_review(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: str,
    diff: dict | None = None,
    reviewer: str | None = None,
    status: str = "pending",
    note: str | None = None,
) -> Review:
    review = Review(
        review_id=f"rev_{uuid4().hex[:12]}",
        target_type=target_type,
        target_id=target_id,
        diff=diff,
        reviewer=reviewer,
        status=status,
        note=note,
    )
    session.add(review)
    await session.commit()
    await session.refresh(review)
    return review


async def list_reviews(
    session: AsyncSession,
    *,
    status: str | None = None,
) -> list[Review]:
    stmt = select(Review).order_by(Review.created_at.desc())
    if status is not None:
        stmt = stmt.where(Review.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_review(
    session: AsyncSession,
    *,
    review_id: str,
) -> Review | None:
    result = await session.execute(
        select(Review).where(Review.review_id == review_id)
    )
    return result.scalar_one_or_none()


async def save_review(
    session: AsyncSession,
    review: Review,
    *,
    diff: dict | None = None,
    reviewer: str | None = None,
    status: str | None = None,
    note: str | None = None,
    reviewed_at=None,
) -> Review:
    if diff is not None:
        review.diff = diff
    if reviewer is not None:
        review.reviewer = reviewer
    if status is not None:
        review.status = status
    if note is not None:
        review.note = note
    if reviewed_at is not None:
        review.reviewed_at = reviewed_at
    await session.commit()
    await session.refresh(review)
    return review
