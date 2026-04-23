from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Event


async def upsert_events(
    session: AsyncSession,
    events: Sequence[dict],
) -> list[Event]:
    stored: list[Event] = []
    for payload in events:
        event = await session.get(Event, payload["event_id"])
        if event is None:
            event = Event(**payload)
            session.add(event)
        else:
            event.title = payload["title"]
            event.description = payload.get("description")
            event.timeline_pos = payload.get("timeline_pos")
            event.participants = payload.get("participants", [])
            event.location = payload.get("location")
            event.emotion_valence = payload.get("emotion_valence")
            event.source_segments = payload.get("source_segments", [])
        stored.append(event)

    await session.commit()
    for event in stored:
        await session.refresh(event)
    return stored


async def list_events_for_character(
    session: AsyncSession,
    *,
    project_id: str,
    character_id: str,
) -> list[Event]:
    result = await session.execute(
        select(Event)
        .where(
            Event.project_id == project_id,
            Event.participants.contains([character_id]),
        )
        .order_by(Event.timeline_pos.asc().nullslast(), Event.created_at.asc())
    )
    return list(result.scalars().all())


async def list_events_for_project(
    session: AsyncSession,
    *,
    project_id: str,
) -> list[Event]:
    result = await session.execute(
        select(Event)
        .where(Event.project_id == project_id)
        .order_by(Event.timeline_pos.asc().nullslast(), Event.created_at.asc())
    )
    return list(result.scalars().all())


async def get_event(
    session: AsyncSession,
    *,
    project_id: str,
    event_id: str,
) -> Event | None:
    result = await session.execute(
        select(Event).where(
            Event.project_id == project_id,
            Event.event_id == event_id,
        )
    )
    return result.scalar_one_or_none()
