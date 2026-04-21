from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.queries.characters import upsert_characters
from camo.db.queries.texts import list_text_segments_for_source
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt

SCHEMA_VERSION = "0.2"


@dataclass(frozen=True)
class CharacterMention:
    name: str
    aliases: list[str]
    titles: list[str]
    identities: list[dict[str, str]]
    description: str
    character_type: str
    segment_id: str
    position: int


async def run_entity_index(
    *,
    session: AsyncSession,
    model_adapter: ModelAdapter,
    project_id: str,
    source_id: str,
    source_type: str,
    segment_limit: int | None = None,
    concurrency: int = 5,
) -> tuple[list, int]:
    segments = await list_text_segments_for_source(session, source_id, limit=segment_limit)
    schema = load_json_schema("schemas/entity_index.json")
    semaphore = asyncio.Semaphore(concurrency)

    async def extract_segment(segment) -> list[CharacterMention]:
        async with semaphore:
            prompt = render_prompt(
                "extraction/entity_index.jinja2",
                source_type=source_type,
                segment_id=segment.segment_id,
                chapter=segment.chapter,
                round_num=segment.round,
                content=segment.content,
            )
            result = await model_adapter.complete(
                messages=[
                    {
                        "role": "system",
                        "content": "你是严格的人物实体识别器，只返回结构化结果。",
                    },
                    {"role": "user", "content": prompt},
                ],
                task="extraction",
                json_schema=schema,
            )
            structured = result.structured or {"schema_version": SCHEMA_VERSION, "characters": []}
            mentions: list[CharacterMention] = []
            for character in structured.get("characters", []):
                name = character.get("name", "").strip()
                if not name:
                    continue
                mentions.append(
                    CharacterMention(
                        name=name,
                        aliases=_clean_text_list(character.get("aliases", [])),
                        titles=_clean_text_list(character.get("titles", [])),
                        identities=_clean_identity_list(character.get("identities", [])),
                        description=str(character.get("description", "")).strip(),
                        character_type=_clean_character_type(
                            character.get("character_type"),
                            fallback=_default_character_type(source_type),
                        ),
                        segment_id=segment.segment_id,
                        position=segment.position,
                    )
                )
            return mentions

    mention_groups = await asyncio.gather(*(extract_segment(segment) for segment in segments))
    mentions = [mention for group in mention_groups for mention in group]
    aggregated = _aggregate_mentions(mentions=mentions, total_segments=len(segments))
    stored = await upsert_characters(session, project_id, aggregated)
    return stored, len(segments)


def _aggregate_mentions(
    *,
    mentions: list[CharacterMention],
    total_segments: int,
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []

    for mention in mentions:
        mention_names = {mention.name, *mention.aliases}
        normalized_mention = {_normalize_text(value) for value in mention_names if value}
        matched_cluster = None
        for cluster in clusters:
            if normalized_mention & cluster["normalized_names"]:
                matched_cluster = cluster
                break

        if matched_cluster is None:
            matched_cluster = {
                "normalized_names": set(),
                "names": set(),
                "aliases": set(),
                "titles": set(),
                "identities": {},
                "descriptions": [],
                "character_type": mention.character_type or "unidentified_person",
                "source_segments": set(),
                "positions": [],
            }
            clusters.append(matched_cluster)

        matched_cluster["normalized_names"].update(normalized_mention)
        matched_cluster["names"].add(mention.name)
        matched_cluster["aliases"].update(alias for alias in mention.aliases if alias and alias != mention.name)
        matched_cluster["titles"].update(title for title in mention.titles if title)
        for identity in mention.identities:
            identity_type = identity.get("type", "").strip()
            identity_value = identity.get("value", "").strip()
            if identity_type and identity_value:
                matched_cluster["identities"][(identity_type, identity_value)] = {
                    "type": identity_type,
                    "value": identity_value,
                }
        if mention.description:
            matched_cluster["descriptions"].append(mention.description)
        matched_cluster["source_segments"].add(mention.segment_id)
        matched_cluster["positions"].append((mention.position, mention.segment_id))

    payloads: list[dict[str, Any]] = []
    for cluster in clusters:
        canonical_name = sorted(cluster["names"], key=lambda item: (len(item), item))[0]
        first_position, first_segment_id = min(cluster["positions"], key=lambda item: item[0])
        unique_segment_count = len(cluster["source_segments"])
        confidence = round(unique_segment_count / total_segments, 3) if total_segments else 0.0
        description = cluster["descriptions"][0] if cluster["descriptions"] else ""
        aliases = sorted(alias for alias in cluster["aliases"] if alias != canonical_name)
        payloads.append(
            {
                "character_id": f"char_{uuid4().hex[:12]}",
                "_sort_position": first_position,
                "index_payload": {
                    "schema_version": SCHEMA_VERSION,
                    "character_type": cluster["character_type"],
                    "name": canonical_name,
                    "description": description,
                    "aliases": aliases,
                    "titles": sorted(cluster["titles"]),
                    "identities": sorted(
                        cluster["identities"].values(),
                        key=lambda item: (item["type"], item["value"]),
                    ),
                    "first_appearance": first_segment_id,
                    "confidence": confidence,
                    "source_segments": sorted(cluster["source_segments"]),
                },
            }
        )

    payloads.sort(key=lambda item: item["_sort_position"])
    for payload in payloads:
        payload.pop("_sort_position", None)
    return payloads


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _clean_text_list(values: list[Any]) -> list[str]:
    cleaned = []
    for value in values:
        text = str(value).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _clean_identity_list(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    cleaned: list[dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        identity_type = str(value.get("type", "")).strip()
        identity_value = str(value.get("value", "")).strip()
        if identity_type and identity_value:
            cleaned.append({"type": identity_type, "value": identity_value})
    return cleaned


def _default_character_type(source_type: str) -> str:
    if source_type == "novel":
        return "fictional_person"
    if source_type == "chat":
        return "real_person"
    return "unidentified_person"


def _clean_character_type(value: Any, *, fallback: str) -> str:
    text = str(value).strip()
    return text or fallback
