from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Relationship


async def upsert_relationships(
    session: AsyncSession,
    relationships: Sequence[dict],
) -> list[Relationship]:
    stored: list[Relationship] = []
    for payload in relationships:
        relationship = await session.get(Relationship, payload["relationship_id"])
        if relationship is None:
            relationship = Relationship(**payload)
            session.add(relationship)
        else:
            relationship.schema_version = payload["schema_version"]
            relationship.source_id = payload["source_id"]
            relationship.target_id = payload["target_id"]
            relationship.relation_category = payload["relation_category"]
            relationship.relation_subtype = payload["relation_subtype"]
            relationship.public_state = payload["public_state"]
            relationship.hidden_state = payload.get("hidden_state")
            relationship.timeline = payload.get("timeline", [])
            relationship.source_segments = payload.get("source_segments", [])
            relationship.confidence = payload.get("confidence")
        stored.append(relationship)

    await session.commit()
    for relationship in stored:
        await session.refresh(relationship)
    return stored


async def list_relationships_for_character(
    session: AsyncSession,
    *,
    project_id: str,
    character_id: str,
) -> list[Relationship]:
    result = await session.execute(
        select(Relationship)
        .where(
            Relationship.project_id == project_id,
            (Relationship.source_id == character_id) | (Relationship.target_id == character_id),
        )
        .order_by(Relationship.updated_at.desc(), Relationship.created_at.desc())
    )
    return list(result.scalars().all())


async def get_relationship(
    session: AsyncSession,
    *,
    project_id: str,
    relationship_id: str,
) -> Relationship | None:
    result = await session.execute(
        select(Relationship).where(
            Relationship.project_id == project_id,
            Relationship.relationship_id == relationship_id,
        )
    )
    return result.scalar_one_or_none()


async def get_relationship_by_id(
    session: AsyncSession,
    *,
    relationship_id: str,
) -> Relationship | None:
    result = await session.execute(
        select(Relationship).where(
            Relationship.relationship_id == relationship_id,
        )
    )
    return result.scalar_one_or_none()
