from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Memory


async def replace_memories_for_character(
    session: AsyncSession,
    *,
    character_id: str,
    memory_types: Sequence[str],
    memories: Sequence[dict],
) -> list[Memory]:
    await session.execute(
        delete(Memory).where(
            Memory.character_id == character_id,
            Memory.memory_type.in_(list(memory_types)),
        )
    )

    stored: list[Memory] = []
    for payload in memories:
        memory = Memory(**payload)
        session.add(memory)
        stored.append(memory)

    await session.commit()
    for memory in stored:
        await session.refresh(memory)
    return stored


async def list_memories_for_character(
    session: AsyncSession,
    *,
    project_id: str,
    character_id: str,
) -> list[Memory]:
    result = await session.execute(
        select(Memory)
        .where(
            Memory.project_id == project_id,
            Memory.character_id == character_id,
        )
        .order_by(Memory.memory_type.asc(), Memory.salience.desc(), Memory.created_at.asc())
    )
    return list(result.scalars().all())
