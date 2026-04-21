from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import TextSegment, TextSource


async def create_text_source(session: AsyncSession, source: TextSource) -> TextSource:
    session.add(source)
    await session.flush()
    return source


async def add_text_segments(session: AsyncSession, segments: list[TextSegment]) -> None:
    session.add_all(segments)
    await session.flush()


async def get_text_source(
    session: AsyncSession,
    project_id: str,
    source_id: str,
) -> TextSource | None:
    result = await session.execute(
        select(TextSource).where(
            TextSource.project_id == project_id,
            TextSource.source_id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def list_text_sources(session: AsyncSession, project_id: str) -> list[TextSource]:
    result = await session.execute(
        select(TextSource)
        .where(TextSource.project_id == project_id)
        .order_by(TextSource.created_at.desc())
    )
    return list(result.scalars().all())


async def list_text_segments(session: AsyncSession, source_id: str) -> list[TextSegment]:
    result = await session.execute(
        select(TextSegment)
        .where(TextSegment.source_id == source_id)
        .order_by(TextSegment.position.asc())
    )
    return list(result.scalars().all())


async def list_text_segments_for_source(
    session: AsyncSession,
    source_id: str,
    *,
    limit: int | None = None,
) -> list[TextSegment]:
    stmt = (
        select(TextSegment)
        .where(TextSegment.source_id == source_id)
        .order_by(TextSegment.position.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
