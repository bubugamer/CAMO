from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Character

SCHEMA_VERSION = "0.2"


async def list_characters(session: AsyncSession, project_id: str) -> list[Character]:
    result = await session.execute(
        select(Character)
        .where(Character.project_id == project_id)
        .order_by(Character.created_at.asc())
    )
    return list(result.scalars().all())


async def get_character(
    session: AsyncSession,
    project_id: str,
    character_id: str,
) -> Character | None:
    result = await session.execute(
        select(Character).where(
            Character.project_id == project_id,
            Character.character_id == character_id,
        )
    )
    return result.scalar_one_or_none()


async def get_character_by_id(
    session: AsyncSession,
    character_id: str,
) -> Character | None:
    result = await session.execute(
        select(Character).where(Character.character_id == character_id)
    )
    return result.scalar_one_or_none()


async def find_character_by_name(
    session: AsyncSession,
    project_id: str,
    *,
    name: str,
    aliases: Sequence[str] = (),
) -> Character | None:
    normalized_candidates = {_normalize_name(name), *(_normalize_name(alias) for alias in aliases)}
    normalized_candidates.discard("")

    for character in await list_characters(session, project_id):
        character_index = character.character_index
        names = {_normalize_name(str(character_index.get("name", "")))}
        names.update(_normalize_name(str(alias)) for alias in character_index.get("aliases", []))
        names.discard("")
        if normalized_candidates & names:
            return character
    return None


async def ensure_character_shell(
    session: AsyncSession,
    project_id: str,
    *,
    source_id: str,
    source_type: str,
    name: str,
    aliases: Sequence[str],
    source_segments: Sequence[str],
) -> Character:
    existing = await find_character_by_name(session, project_id, name=name, aliases=aliases)
    if existing is not None:
        character_index = existing.character_index
        merged_aliases = sorted({*(character_index.get("aliases", [])), *aliases})
        merged_segments = sorted({*(character_index.get("source_segments", [])), *source_segments})
        first_appearance = character_index.get("first_appearance")
        if not first_appearance and merged_segments:
            first_appearance = merged_segments[0]

        character_index["schema_version"] = SCHEMA_VERSION
        character_index["aliases"] = [
            alias for alias in merged_aliases if alias and alias != character_index.get("name", name)
        ]
        character_index["source_segments"] = merged_segments
        character_index["first_appearance"] = first_appearance
        character_index["character_type"] = _normalize_character_type(
            character_index.get("character_type"),
            source_type=source_type,
        )
        character_index["confidence"] = float(character_index.get("confidence", 0.0) or 0.0)
        character_index["titles"] = list(character_index.get("titles", []))
        character_index["identities"] = list(character_index.get("identities", []))
        existing.character_index = character_index
        await session.commit()
        await session.refresh(existing)
        return existing

    character = Character(
        character_id=f"char_{uuid4().hex[:12]}",
        project_id=project_id,
        character_index={
            "schema_version": SCHEMA_VERSION,
            "character_type": _default_character_type(source_type),
            "name": name,
            "description": "",
            "aliases": [alias for alias in aliases if alias and alias != name],
            "titles": [],
            "identities": [],
            "first_appearance": source_segments[0] if source_segments else None,
            "confidence": 0.0,
            "source_segments": list(source_segments),
        },
    )
    session.add(character)
    await session.commit()
    await session.refresh(character)
    return character


async def save_character_portrait(
    session: AsyncSession,
    character: Character,
    *,
    character_core: dict,
    character_facet: dict,
) -> Character:
    character.character_core = character_core
    character.character_facet = character_facet
    await session.commit()
    await session.refresh(character)
    return character


async def save_character_assets(
    session: AsyncSession,
    character: Character,
    *,
    character_index: dict | None = None,
    character_core: dict | None = None,
    character_facet: dict | None = None,
    status: str | None = None,
) -> Character:
    if character_index is not None:
        character.character_index = character_index
    if character_core is not None:
        character.character_core = character_core
    if character_facet is not None:
        character.character_facet = character_facet
    if status is not None:
        character.status = status
    await session.commit()
    await session.refresh(character)
    return character


async def upsert_characters(
    session: AsyncSession,
    project_id: str,
    characters: Sequence[dict],
) -> list[Character]:
    existing = await list_characters(session, project_id)
    stored: list[Character] = []

    for payload in characters:
        match = _match_existing_character(existing, payload)
        if match is None:
            character = Character(
                character_id=payload["character_id"],
                project_id=project_id,
                character_index=payload["character_index"],
            )
            session.add(character)
            existing.append(character)
            stored.append(character)
        else:
            match.character_index = payload["character_index"]
            stored.append(match)

    await session.commit()
    for character in stored:
        await session.refresh(character)
    return stored


def _match_existing_character(existing: list[Character], candidate: dict) -> Character | None:
    candidate_names = {candidate["character_index"]["name"].strip()}
    candidate_names.update(alias.strip() for alias in candidate["character_index"].get("aliases", []))
    normalized_candidate = {name.lower() for name in candidate_names if name}

    for character in existing:
        character_index = character.character_index
        existing_names = {character_index.get("name", "").strip()}
        existing_names.update(alias.strip() for alias in character_index.get("aliases", []))
        normalized_existing = {name.lower() for name in existing_names if name}
        if normalized_candidate & normalized_existing:
            return character
    return None


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _default_character_type(source_type: str) -> str:
    if source_type == "novel":
        return "fictional_person"
    if source_type == "chat":
        return "real_person"
    return "unidentified_person"


def _normalize_character_type(value: str | None, *, source_type: str) -> str:
    text = (value or "").strip()
    if text in {
        "fictional_person",
        "real_person",
        "group_persona",
        "virtual_persona",
        "unnamed_person",
        "unidentified_person",
    }:
        return text
    return _default_character_type(source_type)
