from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import TextSegment, TextSource


@dataclass(frozen=True)
class ProjectSegmentRecord:
    segment: TextSegment
    source: TextSource


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


async def list_project_segment_records(
    session: AsyncSession,
    project_id: str,
) -> list[ProjectSegmentRecord]:
    result = await session.execute(
        select(TextSegment, TextSource)
        .join(TextSource, TextSource.source_id == TextSegment.source_id)
        .where(TextSource.project_id == project_id)
        .order_by(TextSource.created_at.asc(), TextSegment.position.asc())
    )
    rows = result.all()
    return [
        ProjectSegmentRecord(segment=segment, source=source)
        for segment, source in rows
    ]


async def get_project_max_timeline_pos(session: AsyncSession, project_id: str) -> int:
    records = await list_project_segment_records(session, project_id)
    positions = [
        int(record.segment.segment_metadata.get("timeline_pos"))
        for record in records
        if isinstance(record.segment.segment_metadata.get("timeline_pos"), int)
    ]
    if positions:
        return max(positions)
    return len(records)
