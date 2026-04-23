from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import CharacterVersion


async def list_versions_for_character(
    session: AsyncSession,
    *,
    character_id: str,
) -> list[CharacterVersion]:
    result = await session.execute(
        select(CharacterVersion)
        .where(CharacterVersion.character_id == character_id)
        .order_by(CharacterVersion.version_num.desc(), CharacterVersion.created_at.desc())
    )
    return list(result.scalars().all())


async def create_character_version(
    session: AsyncSession,
    *,
    character_id: str,
    snapshot: dict[str, Any],
    diff: dict[str, Any] | None = None,
    created_by: str | None = None,
    note: str | None = None,
) -> CharacterVersion:
    existing = await list_versions_for_character(session, character_id=character_id)
    version = CharacterVersion(
        version_id=f"ver_{uuid4().hex[:12]}",
        character_id=character_id,
        version_num=(existing[0].version_num + 1) if existing else 1,
        snapshot=deepcopy(snapshot),
        diff=deepcopy(diff) if diff is not None else None,
        created_by=created_by,
        note=note,
    )
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version
