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
        payload = character.index_payload
        names = {_normalize_name(str(payload.get("name", "")))}
        names.update(_normalize_name(str(alias)) for alias in payload.get("aliases", []))
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
        payload = existing.index_payload
        merged_aliases = sorted({*(payload.get("aliases", [])), *aliases})
        merged_segments = sorted({*(payload.get("source_segments", [])), *source_segments})
        first_appearance = payload.get("first_appearance")
        if not first_appearance and merged_segments:
            first_appearance = merged_segments[0]

        payload["schema_version"] = SCHEMA_VERSION
        payload["aliases"] = [alias for alias in merged_aliases if alias and alias != payload.get("name", name)]
        payload["source_segments"] = merged_segments
        payload["first_appearance"] = first_appearance
        payload["character_type"] = _normalize_character_type(
            payload.get("character_type"),
            source_type=source_type,
        )
        payload["confidence"] = float(payload.get("confidence", 0.0) or 0.0)
        payload["titles"] = list(payload.get("titles", []))
        payload["identities"] = list(payload.get("identities", []))
        existing.index_payload = payload
        await session.commit()
        await session.refresh(existing)
        return existing

    character = Character(
        character_id=f"char_{uuid4().hex[:12]}",
        project_id=project_id,
        index_payload={
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
    core: dict,
    facet: dict,
) -> Character:
    character.core = core
    character.facet = facet
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
                index_payload=payload["index_payload"],
            )
            session.add(character)
            existing.append(character)
            stored.append(character)
        else:
            match.index_payload = payload["index_payload"]
            stored.append(match)

    await session.commit()
    for character in stored:
        await session.refresh(character)
    return stored


def _match_existing_character(existing: list[Character], candidate: dict) -> Character | None:
    candidate_names = {candidate["index_payload"]["name"].strip()}
    candidate_names.update(alias.strip() for alias in candidate["index_payload"].get("aliases", []))
    normalized_candidate = {name.lower() for name in candidate_names if name}

    for character in existing:
        payload = character.index_payload
        existing_names = {payload.get("name", "").strip()}
        existing_names.update(alias.strip() for alias in payload.get("aliases", []))
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
