from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
import re
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Character, Event, Memory, Relationship, TextSegment
from camo.db.queries.characters import ensure_character_shell, list_characters, save_character_portrait
from camo.db.queries.events import upsert_events
from camo.db.queries.memories import replace_memories_for_character
from camo.db.queries.relationships import upsert_relationships
from camo.db.queries.texts import list_project_segment_records, list_text_segments_for_source
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt

SCHEMA_VERSION = "0.2"
RELATION_STANCES = {"positive", "neutral", "negative"}


@dataclass(frozen=True)
class SegmentEvidence:
    segment_id: str
    position: int
    chapter: str | None
    excerpt: str


async def run_character_portrait(
    *,
    session: AsyncSession,
    model_adapter: ModelAdapter,
    project_id: str,
    source_id: str,
    source_type: str,
    name: str,
    aliases: list[str] | None = None,
    max_segments: int = 12,
) -> tuple[Character, list[Relationship], list[Event], list[Memory], int, list[str]]:
    resolved_aliases = [alias for alias in (aliases or []) if alias and alias != name]
    segments = await list_text_segments_for_source(session, source_id)
    evidence = select_character_evidence(
        segments,
        keywords=[name, *resolved_aliases],
        max_segments=max_segments,
    )
    if not evidence:
        raise ValueError(f"No matching segments found for character '{name}'")

    character = await ensure_character_shell(
        session,
        project_id,
        source_id=source_id,
        source_type=source_type,
        name=name,
        aliases=resolved_aliases,
        source_segments=[item.segment_id for item in evidence],
    )
    project_characters = await list_characters(session, project_id)
    name_lookup = _build_character_lookup(project_characters)
    segment_lookup = {segment.segment_id: segment for segment in segments}

    schema = load_json_schema("schemas/character_portrait_extraction.json")
    prompt = render_prompt(
        "extraction/character_portrait.jinja2",
        character_name=name,
        aliases=resolved_aliases,
        known_character_list=[
            {
                "character_id": item.character_id,
                "name": item.character_index.get("name", ""),
                "aliases": item.character_index.get("aliases", []),
            }
            for item in project_characters
        ],
        evidence_segments=[
            {
                "segment_id": item.segment_id,
                "position": item.position,
                "chapter": item.chapter,
                "excerpt": item.excerpt,
            }
            for item in evidence
        ],
    )
    result = await model_adapter.complete(
        messages=[
            {
                "role": "system",
                "content": "你是严谨的小说人物画像分析器。只能根据给定证据总结，不要使用外部知识。",
            },
            {"role": "user", "content": prompt},
        ],
        task="aggregation",
        json_schema=schema,
    )
    structured = result.structured or {}
    normalized_payload = _normalize_portrait_payload(
        structured,
        source_ids=[source_id],
        character_id=character.character_id,
        segment_lookup=segment_lookup,
    )
    character_core = normalized_payload["character_core"]
    character_facet = normalized_payload["character_facet"]
    await save_character_portrait(
        session,
        character,
        character_core=character_core,
        character_facet=character_facet,
    )

    relationship_payloads = _build_relationship_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_relationships=normalized_payload["relationships"],
        name_lookup=name_lookup,
    )
    stored_relationships = await upsert_relationships(session, relationship_payloads) if relationship_payloads else []

    event_payloads = _build_event_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_events=normalized_payload["events"],
        name_lookup=name_lookup,
    )
    stored_events = await upsert_events(session, event_payloads) if event_payloads else []
    event_title_map = {event.title: event.event_id for event in stored_events}

    memory_payloads = _build_memory_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_memories=normalized_payload["memories"],
        name_lookup=name_lookup,
        event_title_map=event_title_map,
    )
    memory_payloads = await _attach_memory_embeddings(model_adapter, memory_payloads)
    stored_memories = await replace_memories_for_character(
        session,
        character_id=character.character_id,
        memory_types=["profile", "episodic"],
        memories=memory_payloads,
    )
    await session.refresh(character)
    return (
        character,
        stored_relationships,
        stored_events,
        stored_memories,
        len(evidence),
        [item.segment_id for item in evidence],
    )


async def run_project_character_portrait(
    *,
    session: AsyncSession,
    model_adapter: ModelAdapter,
    project_id: str,
    name: str,
    aliases: list[str] | None = None,
    max_segments_per_chapter: int = 10,
    progress_callback: Callable[[str, str | None], Awaitable[None]] | None = None,
) -> tuple[Character, list[Relationship], list[Event], list[Memory], int, list[str]]:
    resolved_aliases = [alias for alias in (aliases or []) if alias and alias != name]
    records = await list_project_segment_records(session, project_id)
    segments = [record.segment for record in records]
    evidence = select_character_evidence(
        segments,
        keywords=[name, *resolved_aliases],
        max_segments=max(1, len(segments)),
    )
    if not evidence:
        raise ValueError(f"No matching segments found for character '{name}'")

    evidence_record_lookup = {record.segment.segment_id: record for record in records}
    first_record = evidence_record_lookup[evidence[0].segment_id]
    character = await ensure_character_shell(
        session,
        project_id,
        source_id=first_record.source.source_id,
        source_type=first_record.source.source_type,
        name=name,
        aliases=resolved_aliases,
        source_segments=[item.segment_id for item in evidence],
    )
    project_characters = await list_characters(session, project_id)
    name_lookup = _build_character_lookup(project_characters)
    segment_lookup = {segment.segment_id: segment for segment in segments}
    source_ids = sorted({evidence_record_lookup[item.segment_id].source.source_id for item in evidence})
    chapter_groups = group_evidence_by_chapter(
        evidence,
        segment_lookup=segment_lookup,
        max_segments_per_chapter=max_segments_per_chapter,
    )
    known_character_list = [
        {
            "character_id": item.character_id,
            "name": item.character_index.get("name", ""),
            "aliases": item.character_index.get("aliases", []),
        }
        for item in project_characters
    ]
    chapter_payloads: list[dict[str, Any]] = []
    for chapter_key, chapter_evidence in chapter_groups:
        if progress_callback is not None:
            await progress_callback("pass2_chapter_aggregate", chapter_key)
        chapter_payloads.append(
            build_chapter_payload(
                chapter_key=chapter_key,
                evidence=chapter_evidence,
                segment_lookup=segment_lookup,
                character_name=name,
                aliases=resolved_aliases,
                known_character_list=known_character_list,
            )
        )
    merged_payload = merge_chapter_payloads(chapter_payloads)
    if progress_callback is not None:
        await progress_callback("pass2_book_resolve", None)
    resolved_payload = await resolve_book_level_conflicts(
        model_adapter=model_adapter,
        character_name=name,
        aliases=resolved_aliases,
        known_character_list=known_character_list,
        merged_payload=merged_payload,
    )
    normalized_payload = finalize_character_assets(
        resolved_payload,
        source_ids=source_ids,
        character_id=character.character_id,
        segment_lookup=segment_lookup,
    )
    character_core = normalized_payload["character_core"]
    character_facet = normalized_payload["character_facet"]
    await save_character_portrait(
        session,
        character,
        character_core=character_core,
        character_facet=character_facet,
    )

    relationship_payloads = _build_relationship_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_relationships=normalized_payload["relationships"],
        name_lookup=name_lookup,
    )
    stored_relationships = await upsert_relationships(session, relationship_payloads) if relationship_payloads else []

    event_payloads = _build_event_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_events=normalized_payload["events"],
        name_lookup=name_lookup,
    )
    stored_events = await upsert_events(session, event_payloads) if event_payloads else []
    event_title_map = {event.title: event.event_id for event in stored_events}

    memory_payloads = _build_memory_payloads(
        project_id=project_id,
        character_id=character.character_id,
        extracted_memories=normalized_payload["memories"],
        name_lookup=name_lookup,
        event_title_map=event_title_map,
    )
    memory_payloads = await _attach_memory_embeddings(model_adapter, memory_payloads)
    stored_memories = await replace_memories_for_character(
        session,
        character_id=character.character_id,
        memory_types=["profile", "episodic"],
        memories=memory_payloads,
    )
    await session.refresh(character)
    return (
        character,
        stored_relationships,
        stored_events,
        stored_memories,
        len(evidence),
        [item.segment_id for item in evidence],
    )


def group_evidence_by_chapter(
    evidence: list[SegmentEvidence],
    *,
    segment_lookup: dict[str, TextSegment],
    max_segments_per_chapter: int,
) -> list[tuple[str, list[SegmentEvidence]]]:
    buckets: dict[str, list[SegmentEvidence]] = {}
    for item in evidence:
        segment = segment_lookup[item.segment_id]
        chapter_key = _resolve_chapter_key(segment)
        buckets.setdefault(chapter_key, []).append(item)

    grouped = [
        (
            chapter_key,
            items if len(items) <= max_segments_per_chapter else [items[index] for index in _sample_even_indices(len(items), max_segments_per_chapter)],
        )
        for chapter_key, items in buckets.items()
    ]
    grouped.sort(key=lambda item: min(evidence.position for evidence in item[1]))
    return grouped


def build_chapter_payload(
    *,
    chapter_key: str,
    evidence: list[SegmentEvidence],
    segment_lookup: dict[str, TextSegment],
    character_name: str,
    aliases: list[str],
    known_character_list: list[dict[str, Any]],
) -> dict[str, Any]:
    chapter_segments = [
        {
            "segment_id": item.segment_id,
            "position": item.position,
            "chapter": item.chapter,
            "timeline_pos": _resolve_segment_timeline_pos(segment_lookup[item.segment_id]),
            "excerpt": item.excerpt,
        }
        for item in evidence
    ]
    known_name_lookup = _build_known_name_lookup(
        known_character_list=known_character_list,
        character_name=character_name,
        aliases=aliases,
    )
    relationship_mentions = _build_chapter_relationship_mentions(
        chapter_segments,
        known_name_lookup,
        chapter_key=chapter_key,
    )
    motivation_evidence = [
        {
            "segment_id": item["segment_id"],
            "excerpt": item["excerpt"],
        }
        for item in chapter_segments
        if _looks_like_motivation_excerpt(item["excerpt"])
    ]
    if not motivation_evidence:
        motivation_evidence = [
            {"segment_id": item["segment_id"], "excerpt": item["excerpt"]}
            for item in chapter_segments[:2]
        ]

    source_segments = [item["segment_id"] for item in chapter_segments]
    summary_excerpt = chapter_segments[0]["excerpt"] if chapter_segments else ""
    timeline_pos = min(item["timeline_pos"] for item in chapter_segments) if chapter_segments else 1
    return {
        "chapter_key": chapter_key,
        "source_segments": source_segments,
        "trait_evidence": [
            {"segment_id": item["segment_id"], "excerpt": item["excerpt"]}
            for item in chapter_segments
        ],
        "motivation_evidence": motivation_evidence,
        "relationship_mentions": relationship_mentions,
        "events": [
            {
                "title": _build_event_candidate_title(chapter_key, summary_excerpt),
                "timeline_pos": timeline_pos,
                "source_segments": source_segments,
                "excerpt": summary_excerpt,
            }
        ]
        if chapter_segments
        else [],
        "memories": [
            {
                "content": item["excerpt"],
                "source_event_id": None,
                "source_segments": [item["segment_id"]],
            }
            for item in chapter_segments[:3]
        ],
        "temporal_snapshot_candidates": [
            {
                "period_label": chapter_key,
                "source_segments": source_segments,
                "stage_summary": summary_excerpt[:160],
                "timeline_pos": timeline_pos,
            }
        ]
        if chapter_segments
        else [],
        "evidence_segments": chapter_segments,
    }


def merge_chapter_payloads(chapter_payloads: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "chapter_payloads": chapter_payloads,
        "trait_evidence": [],
        "motivation_evidence": [],
        "relationship_mentions": [],
        "events": [],
        "memories": [],
        "temporal_snapshot_candidates": [],
        "source_segments": [],
    }
    seen_trait_segments: set[str] = set()
    seen_motivation_segments: set[str] = set()
    seen_relationships: set[tuple[str, str]] = set()
    seen_events: set[tuple[int, str]] = set()
    seen_memories: set[tuple[str, str | None]] = set()
    merged_segments: set[str] = set()

    for payload in chapter_payloads:
        for item in payload.get("trait_evidence", []):
            segment_id = str(item.get("segment_id", "")).strip()
            if segment_id and segment_id not in seen_trait_segments:
                seen_trait_segments.add(segment_id)
                merged["trait_evidence"].append(item)

        for item in payload.get("motivation_evidence", []):
            segment_id = str(item.get("segment_id", "")).strip()
            if segment_id and segment_id not in seen_motivation_segments:
                seen_motivation_segments.add(segment_id)
                merged["motivation_evidence"].append(item)

        for item in payload.get("relationship_mentions", []):
            target_name = str(item.get("target_name", "")).strip()
            relationship_key = (target_name, str(item.get("chapter_key", payload.get("chapter_key", ""))).strip())
            if target_name and relationship_key not in seen_relationships:
                seen_relationships.add(relationship_key)
                merged["relationship_mentions"].append(item)

        for item in payload.get("events", []):
            title = str(item.get("title", "")).strip()
            timeline_pos = int(item.get("timeline_pos", 0) or 0)
            event_key = (timeline_pos, title)
            if title and event_key not in seen_events:
                seen_events.add(event_key)
                merged["events"].append(item)

        for item in payload.get("memories", []):
            content = str(item.get("content", "")).strip()
            source_event_id = item.get("source_event_id")
            memory_key = (content, str(source_event_id) if source_event_id is not None else None)
            if content and memory_key not in seen_memories:
                seen_memories.add(memory_key)
                merged["memories"].append(item)

        for item in payload.get("temporal_snapshot_candidates", []):
            merged["temporal_snapshot_candidates"].append(item)

        for segment_id in payload.get("source_segments", []):
            segment_text = str(segment_id).strip()
            if segment_text:
                merged_segments.add(segment_text)

    merged["temporal_snapshot_candidates"].sort(
        key=lambda item: (int(item.get("timeline_pos", 0) or 0), str(item.get("period_label", "")))
    )
    merged["source_segments"] = sorted(merged_segments)
    return merged


async def resolve_book_level_conflicts(
    *,
    model_adapter: ModelAdapter,
    character_name: str,
    aliases: list[str],
    known_character_list: list[dict[str, Any]],
    merged_payload: dict[str, Any],
) -> dict[str, Any]:
    schema = load_json_schema("schemas/character_portrait_conflict.json")
    prompt = render_prompt(
        "extraction/character_portrait_conflict.jinja2",
        character_name=character_name,
        aliases=aliases,
        known_character_list=known_character_list,
        merged_payload=merged_payload,
    )
    result = await model_adapter.complete(
        messages=[
            {
                "role": "system",
                "content": "你是严谨的人物画像冲突解决器。只能根据章节聚合后的证据结构生成最终画像。",
            },
            {"role": "user", "content": prompt},
        ],
        task="aggregation",
        json_schema=schema,
    )
    return result.structured or {}


def finalize_character_assets(
    payload: dict[str, Any],
    *,
    source_ids: list[str],
    character_id: str,
    segment_lookup: dict[str, TextSegment],
) -> dict[str, Any]:
    return _normalize_portrait_payload(
        payload,
        source_ids=source_ids,
        character_id=character_id,
        segment_lookup=segment_lookup,
    )


def _resolve_chapter_key(segment: TextSegment) -> str:
    if segment.chapter:
        return segment.chapter
    if segment.round is not None:
        return f"{segment.source_id}#round-{segment.round}"
    window_index = ((segment.position - 1) // 8) + 1
    return f"{segment.source_id}#window-{window_index}"


def _build_known_name_lookup(
    *,
    known_character_list: list[dict[str, Any]],
    character_name: str,
    aliases: list[str],
) -> dict[str, str]:
    self_names = {character_name.strip(), *(alias.strip() for alias in aliases if alias.strip())}
    self_names.discard("")
    lookup: dict[str, str] = {}
    for item in known_character_list:
        display_name = str(item.get("name", "")).strip()
        for name in [display_name, *item.get("aliases", [])]:
            raw_name = str(name).strip()
            if not raw_name or raw_name in self_names:
                continue
            lookup[raw_name] = display_name or raw_name
    return lookup


def _build_chapter_relationship_mentions(
    chapter_segments: list[dict[str, Any]],
    known_name_lookup: dict[str, str],
    *,
    chapter_key: str,
) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in chapter_segments:
        excerpt = str(item.get("excerpt", "")).strip()
        if not excerpt:
            continue
        for seen_name, display_name in known_name_lookup.items():
            if not seen_name or seen_name not in excerpt:
                continue
            key = (display_name, str(item.get("segment_id", "")).strip())
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                {
                    "target_name": display_name,
                    "chapter_key": chapter_key,
                    "source_segments": [item.get("segment_id")],
                    "excerpt": excerpt,
                }
            )
    return mentions


def _looks_like_motivation_excerpt(excerpt: str) -> bool:
    return any(keyword in excerpt for keyword in ("想", "要", "欲", "愿", "决定", "打算", "企图", "图谋", "不得不"))


def _build_event_candidate_title(chapter_key: str, excerpt: str) -> str:
    summary = excerpt.replace("...", "").strip()
    if len(summary) > 18:
        summary = summary[:18].rstrip("，。！？；：")
    return summary or chapter_key


def select_character_evidence(
    segments: list[TextSegment],
    *,
    keywords: list[str],
    max_segments: int,
    excerpt_chars: int = 420,
) -> list[SegmentEvidence]:
    cleaned_keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
    matches: list[SegmentEvidence] = []

    for segment in segments:
        excerpt = _extract_excerpt(segment.content, cleaned_keywords, excerpt_chars=excerpt_chars)
        if excerpt is None:
            continue
        matches.append(
            SegmentEvidence(
                segment_id=segment.segment_id,
                position=segment.position,
                chapter=segment.chapter,
                excerpt=excerpt,
            )
        )

    if len(matches) <= max_segments:
        return matches
    selected_indices = _sample_even_indices(len(matches), max_segments)
    return [matches[index] for index in selected_indices]


def _extract_excerpt(content: str, keywords: list[str], *, excerpt_chars: int) -> str | None:
    first_hit = -1
    hit_keyword = ""
    for keyword in keywords:
        index = content.find(keyword)
        if index != -1 and (first_hit == -1 or index < first_hit):
            first_hit = index
            hit_keyword = keyword
    if first_hit == -1:
        return None

    half_window = excerpt_chars // 2
    start = max(0, first_hit - half_window)
    end = min(len(content), first_hit + len(hit_keyword) + half_window)
    excerpt = content[start:end].strip()
    if start > 0:
        excerpt = "..." + excerpt
    if end < len(content):
        excerpt = excerpt + "..."
    return excerpt


def _sample_even_indices(total: int, limit: int) -> list[int]:
    if limit >= total:
        return list(range(total))
    if limit == 1:
        return [0]

    indices = {0, total - 1}
    for slot in range(1, limit - 1):
        index = round(slot * (total - 1) / (limit - 1))
        indices.add(index)
    return sorted(indices)[:limit]


def _build_character_lookup(characters: list[Character]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for character in characters:
        character_index = character.character_index
        for name in [character_index.get("name", ""), *character_index.get("aliases", [])]:
            normalized = _normalize_name(str(name))
            if normalized:
                lookup[normalized] = character.character_id
    return lookup


def _build_relationship_payloads(
    *,
    project_id: str,
    character_id: str,
    extracted_relationships: list[dict[str, Any]],
    name_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for relationship in extracted_relationships:
        target_name = _normalize_name(str(relationship.get("target_name", "")))
        if not target_name or target_name not in name_lookup:
            continue
        target_id = name_lookup[target_name]
        if target_id == character_id:
            continue

        relation_category = str(relationship.get("relation_category", "")).strip()
        relation_subtype = str(relationship.get("relation_subtype", "")).strip()
        if not relation_category or not relation_subtype:
            continue

        source_segments = _clean_string_list(relationship.get("source_segments", []))
        payloads.append(
            {
                "relationship_id": (
                    f"rel_{_hash_id(project_id, character_id, target_id, relation_category, relation_subtype)}"
                ),
                "project_id": project_id,
                "schema_version": str(relationship.get("schema_version", SCHEMA_VERSION)).strip() or SCHEMA_VERSION,
                "source_id": character_id,
                "target_id": target_id,
                "relation_category": relation_category,
                "relation_subtype": relation_subtype,
                "public_state": _normalize_relationship_state(relationship.get("public_state")),
                "hidden_state": _normalize_relationship_state(relationship.get("hidden_state"), allow_empty=True),
                "timeline": relationship.get("timeline", []) if isinstance(relationship.get("timeline"), list) else [],
                "source_segments": source_segments,
                "confidence": _clean_score(relationship.get("confidence"), default=0.5),
            }
        )
    return payloads


def _build_event_payloads(
    *,
    project_id: str,
    character_id: str,
    extracted_events: list[dict[str, Any]],
    name_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for index, event in enumerate(extracted_events, start=1):
        title = str(event.get("title", "")).strip()
        if not title:
            continue
        participants = {
            character_id,
            *(
                name_lookup[name]
                for name in (_normalize_name(item) for item in event.get("participant_names", []))
                if name in name_lookup
            ),
        }
        source_segments = _clean_string_list(event.get("source_segments", []))
        event_id = f"evt_{_hash_id(project_id, character_id, title, *source_segments)}"
        payloads.append(
            {
                "event_id": event_id,
                "project_id": project_id,
                "schema_version": str(event.get("schema_version", SCHEMA_VERSION)).strip() or SCHEMA_VERSION,
                "title": title,
                "description": _clean_optional_text(event.get("description")),
                "timeline_pos": event.get("timeline_pos") if isinstance(event.get("timeline_pos"), int) else index,
                "participants": sorted(participants),
                "location": _clean_optional_text(event.get("location")),
                "emotion_valence": _clean_optional_text(event.get("emotion_valence")),
                "source_segments": source_segments,
            }
        )
    return payloads


def _build_memory_payloads(
    *,
    project_id: str,
    character_id: str,
    extracted_memories: list[dict[str, Any]],
    name_lookup: dict[str, str],
    event_title_map: dict[str, str],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for memory in extracted_memories:
        content = str(memory.get("content", "")).strip()
        memory_type = str(memory.get("memory_type", "")).strip()
        if not content or memory_type not in {"profile", "episodic"}:
            continue
        source_segments = _clean_string_list(memory.get("source_segments", []))
        payloads.append(
            {
                "memory_id": f"mem_{_hash_id(character_id, memory_type, content)}",
                "character_id": character_id,
                "project_id": project_id,
                "schema_version": str(memory.get("schema_version", SCHEMA_VERSION)).strip() or SCHEMA_VERSION,
                "memory_type": memory_type,
                "salience": _clean_score(memory.get("salience"), default=0.6),
                "recency": _clean_score(memory.get("recency"), default=0.8),
                "content": content,
                "source_event_id": event_title_map.get(str(memory.get("source_event_title", "")).strip()),
                "related_character_ids": sorted(
                    {
                        name_lookup[name]
                        for name in (_normalize_name(item) for item in memory.get("related_character_names", []))
                        if name in name_lookup and name_lookup[name] != character_id
                    }
                ),
                "emotion_valence": _clean_optional_text(memory.get("emotion_valence")),
                "source_segments": source_segments,
                "embedding": None,
            }
        )
    return payloads


def _clean_optional_text(value: Any) -> str | None:
    text = str(value).strip()
    return text or None


def _clean_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if text:
            result.append(text)
    return result


def _clean_score(value: Any, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(score, 1.0))


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _hash_id(*parts: str) -> str:
    digest = sha1("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def _slugify(value: str) -> str:
    collapsed = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip())
    return collapsed.strip("_").lower() or "character"


def _normalize_portrait_payload(
    payload: dict[str, Any],
    *,
    source_ids: list[str],
    character_id: str,
    segment_lookup: dict[str, TextSegment],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "character_core": _normalize_character_core(payload.get("character_core", {})),
        "character_facet": _normalize_character_facet(
            payload.get("character_facet", {}),
            source_ids=source_ids,
            character_id=character_id,
            segment_lookup=segment_lookup,
        ),
        "relationships": _normalize_relationships(
            payload.get("relationships", []),
            character_facet=payload.get("character_facet", {}),
            character_id=character_id,
            segment_lookup=segment_lookup,
        ),
        "events": _normalize_events(payload.get("events", []), segment_lookup=segment_lookup),
        "memories": _normalize_memories(payload.get("memories", [])),
    }


def _normalize_character_core(character_core: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "trait_profile": {
            "openness": _clean_int_score(character_core.get("trait_profile", {}).get("openness")),
            "conscientiousness": _clean_int_score(
                character_core.get("trait_profile", {}).get("conscientiousness")
            ),
            "extraversion": _clean_int_score(character_core.get("trait_profile", {}).get("extraversion")),
            "agreeableness": _clean_int_score(character_core.get("trait_profile", {}).get("agreeableness")),
            "neuroticism": _clean_int_score(character_core.get("trait_profile", {}).get("neuroticism")),
        },
        "motivation_profile": {
            "primary": _clean_string_list(character_core.get("motivation_profile", {}).get("primary", [])),
            "secondary": _clean_string_list(
                character_core.get("motivation_profile", {}).get("secondary", [])
            ),
            "suppressed": _clean_string_list(
                character_core.get("motivation_profile", {}).get("suppressed", [])
            ),
        },
        "behavior_profile": {
            "conflict_style": str(
                character_core.get("behavior_profile", {}).get("conflict_style", "")
            ).strip(),
            "risk_preference": str(
                character_core.get("behavior_profile", {}).get("risk_preference", "")
            ).strip(),
            "decision_style": str(
                character_core.get("behavior_profile", {}).get("decision_style", "")
            ).strip(),
            "dominance_style": str(
                character_core.get("behavior_profile", {}).get("dominance_style", "")
            ).strip(),
        },
        "communication_profile": {
            "tone": str(character_core.get("communication_profile", {}).get("tone", "")).strip(),
            "directness": str(character_core.get("communication_profile", {}).get("directness", "")).strip(),
            "emotional_expressiveness": str(
                character_core.get("communication_profile", {}).get("emotional_expressiveness", "")
            ).strip(),
            "verbosity": str(character_core.get("communication_profile", {}).get("verbosity", "")).strip(),
            "politeness": str(character_core.get("communication_profile", {}).get("politeness", "")).strip(),
        },
        "constraint_profile": {
            "knowledge_scope": str(
                character_core.get("constraint_profile", {}).get("knowledge_scope", "")
            ).strip(),
            "role_consistency": str(
                character_core.get("constraint_profile", {}).get("role_consistency", "")
            ).strip(),
            "forbidden_behaviors": [
                {
                    "namespace": str(item.get("namespace", "")).strip(),
                    "tag": str(item.get("tag", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                }
                for item in character_core.get("constraint_profile", {}).get("forbidden_behaviors", [])
                if isinstance(item, dict)
                and str(item.get("namespace", "")).strip()
                and str(item.get("tag", "")).strip()
                and str(item.get("description", "")).strip()
            ],
        },
}


def _normalize_character_facet(
    character_facet: dict[str, Any],
    *,
    source_ids: list[str],
    character_id: str,
    segment_lookup: dict[str, TextSegment],
) -> dict[str, Any]:
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for field_path, entries in (character_facet.get("evidence_map", {}) or {}).items():
        if not isinstance(entries, list):
            continue
        evidence_map[str(field_path)] = [
            {
                "segment_ids": _clean_string_list(entry.get("segment_ids", [])),
                "excerpt": str(entry.get("excerpt", "")).strip(),
                "confidence": _clean_score(entry.get("confidence"), default=0.0),
                "reasoning": str(entry.get("reasoning", "")).strip(),
            }
            for entry in entries
            if isinstance(entry, dict)
            and _clean_string_list(entry.get("segment_ids", []))
            and str(entry.get("excerpt", "")).strip()
            and str(entry.get("reasoning", "")).strip()
        ]

    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_map": evidence_map,
        "biographical_notes": {
            "appearance": str(character_facet.get("biographical_notes", {}).get("appearance", "")).strip(),
            "backstory": str(character_facet.get("biographical_notes", {}).get("backstory", "")).strip(),
            "signature_habits": _clean_string_list(
                character_facet.get("biographical_notes", {}).get("signature_habits", [])
            ),
            "catchphrases": _clean_string_list(
                character_facet.get("biographical_notes", {}).get("catchphrases", [])
            ),
        },
        "temporal_snapshots": _normalize_temporal_snapshots(
            character_facet.get("temporal_snapshots", []),
            character_id=character_id,
            segment_lookup=segment_lookup,
        ),
        "extraction_meta": {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_texts": sorted({source_id for source_id in source_ids if source_id}),
            "reviewer_status": str(
                character_facet.get("extraction_meta", {}).get("reviewer_status", "")
            ).strip()
            or "unreviewed",
            "reviewer_notes": str(
                character_facet.get("extraction_meta", {}).get("reviewer_notes", "")
            ).strip(),
            "schema_version": SCHEMA_VERSION,
        },
    }


def _normalize_temporal_snapshots(
    snapshots: Any,
    *,
    character_id: str,
    segment_lookup: dict[str, TextSegment],
) -> list[dict[str, Any]]:
    if not isinstance(snapshots, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(snapshots, start=1):
        if not isinstance(item, dict):
            continue

        period_label = str(item.get("period_label", "")).strip()
        if not period_label:
            continue

        source_segments = _clean_string_list(item.get("source_segments", []))
        if not source_segments:
            source_segments = _clean_string_list(item.get("period_source", []))

        start_timeline_pos, end_timeline_pos = _resolve_activation_range(source_segments, segment_lookup, fallback=index)
        snapshot_id = str(item.get("snapshot_id", "")).strip() or (
            f"snap_{_slugify(character_id)}_{start_timeline_pos:04d}_{end_timeline_pos:04d}"
        )
        display_hint = item.get("display_hint", {}) if isinstance(item.get("display_hint"), dict) else {}
        normalized.append(
            {
                "snapshot_id": snapshot_id,
                "period_label": period_label,
                "activation_range": {
                    "start_timeline_pos": start_timeline_pos,
                    "end_timeline_pos": end_timeline_pos,
                },
                "display_hint": {
                    "primary": str(display_hint.get("primary", "")).strip() or period_label,
                    "secondary": str(display_hint.get("secondary", "")).strip(),
                },
                "stage_summary": str(item.get("stage_summary", "")).strip(),
                "known_facts": _clean_string_list(item.get("known_facts", [])),
                "unknown_facts": _clean_string_list(item.get("unknown_facts", [])),
                "profile_overrides": item.get("profile_overrides", {})
                if isinstance(item.get("profile_overrides"), dict)
                else {},
                "notes": str(item.get("notes", "")).strip(),
            }
        )

    normalized.sort(
        key=lambda item: (
            item["activation_range"]["start_timeline_pos"],
            item["activation_range"]["end_timeline_pos"],
        )
    )
    return normalized


def _normalize_relationships(
    relationships: Any,
    *,
    character_facet: dict[str, Any],
    character_id: str,
    segment_lookup: dict[str, TextSegment],
) -> list[dict[str, Any]]:
    if not isinstance(relationships, list):
        return []

    snapshots = _normalize_temporal_snapshots(
        character_facet.get("temporal_snapshots", []),
        character_id=character_id,
        segment_lookup=segment_lookup,
    )
    normalized: list[dict[str, Any]] = []
    for item in relationships:
        if not isinstance(item, dict):
            continue

        target_name = str(item.get("target_name", "")).strip()
        relation_category = str(item.get("relation_category", "")).strip()
        relation_subtype = str(item.get("relation_subtype", "")).strip()
        if not target_name or not relation_category or not relation_subtype:
            continue

        source_segments = _clean_string_list(item.get("source_segments", []))
        normalized.append(
            {
                "schema_version": SCHEMA_VERSION,
                "target_name": target_name,
                "relation_category": relation_category,
                "relation_subtype": relation_subtype,
                "public_state": _normalize_relationship_state(item.get("public_state")),
                "hidden_state": _normalize_relationship_state(item.get("hidden_state"), allow_empty=True),
                "timeline": _normalize_relationship_timeline(
                    item.get("timeline", []),
                    source_segments=source_segments,
                    snapshots=snapshots,
                    segment_lookup=segment_lookup,
                ),
                "source_segments": source_segments,
                "confidence": _clean_score(item.get("confidence"), default=0.5),
            }
        )

    return normalized


def _normalize_relationship_timeline(
    timeline: Any,
    *,
    source_segments: list[str],
    snapshots: list[dict[str, Any]],
    segment_lookup: dict[str, TextSegment],
) -> list[dict[str, Any]]:
    if not isinstance(timeline, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(timeline, start=1):
        if not isinstance(item, dict):
            continue

        item_segments = _clean_string_list(item.get("source_segments", [])) or source_segments
        start_timeline_pos, end_timeline_pos = _resolve_activation_range(
            item_segments,
            segment_lookup,
            fallback=index,
        )
        period_label = str(item.get("period_label", "")).strip()
        normalized.append(
            {
                "effective_range": {
                    "start_timeline_pos": start_timeline_pos,
                    "end_timeline_pos": end_timeline_pos,
                },
                "snapshot_id": _match_snapshot_id(
                    snapshots=snapshots,
                    period_label=period_label,
                    start_timeline_pos=start_timeline_pos,
                    end_timeline_pos=end_timeline_pos,
                ),
                "public_state": _normalize_relationship_state(item.get("public_state")),
                "hidden_state": _normalize_relationship_state(item.get("hidden_state"), allow_empty=True),
                "source_segments": item_segments,
            }
        )

    return normalized


def _normalize_relationship_state(value: Any, *, allow_empty: bool = False) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None if allow_empty else {"strength": 50, "stance": "neutral", "notes": ""}

    notes = str(value.get("notes", "")).strip()
    strength_raw = value.get("strength", 50)
    try:
        strength = int(strength_raw)
    except (TypeError, ValueError):
        strength = 50
    stance = str(value.get("stance", "neutral")).strip().lower()
    if stance not in RELATION_STANCES:
        stance = "neutral"

    normalized = {
        "strength": max(0, min(strength, 100)),
        "stance": stance,
        "notes": notes,
    }
    if allow_empty and not notes and normalized["strength"] == 50 and stance == "neutral":
        return None
    return normalized


def _match_snapshot_id(
    *,
    snapshots: list[dict[str, Any]],
    period_label: str,
    start_timeline_pos: int,
    end_timeline_pos: int,
) -> str:
    for snapshot in snapshots:
        if period_label and snapshot.get("period_label") == period_label:
            return str(snapshot.get("snapshot_id", ""))

    for snapshot in snapshots:
        activation_range = snapshot.get("activation_range", {})
        snapshot_start = activation_range.get("start_timeline_pos")
        snapshot_end = activation_range.get("end_timeline_pos")
        if snapshot_start is None or snapshot_end is None:
            continue
        if snapshot_start <= end_timeline_pos and snapshot_end >= start_timeline_pos:
            return str(snapshot.get("snapshot_id", ""))

    return ""


def _resolve_activation_range(
    source_segments: list[str],
    segment_lookup: dict[str, TextSegment],
    *,
    fallback: int,
) -> tuple[int, int]:
    positions = [
        _resolve_segment_timeline_pos(segment_lookup[segment_id])
        for segment_id in source_segments
        if segment_id in segment_lookup
    ]
    if positions:
        return min(positions), max(positions)
    return fallback, fallback


def _resolve_segment_timeline_pos(segment: TextSegment) -> int:
    metadata = getattr(segment, "segment_metadata", {}) or {}
    timeline_pos = metadata.get("timeline_pos")
    if isinstance(timeline_pos, int):
        return timeline_pos
    return segment.position


def _normalize_events(events: list[dict[str, Any]], *, segment_lookup: dict[str, TextSegment]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue
        title = str(event.get("title", "")).strip()
        if not title:
            continue
        source_segments = _clean_string_list(event.get("source_segments", []))
        start_timeline_pos, _ = _resolve_activation_range(source_segments, segment_lookup, fallback=index)
        normalized.append(
            {
                "schema_version": SCHEMA_VERSION,
                "title": title,
                "description": str(event.get("description", "")).strip(),
                "timeline_pos": (
                    event.get("timeline_pos") if isinstance(event.get("timeline_pos"), int) else start_timeline_pos
                ),
                "participant_names": _clean_string_list(event.get("participant_names", [])),
                "location": str(event.get("location", "")).strip(),
                "emotion_valence": str(event.get("emotion_valence", "")).strip(),
                "source_segments": source_segments,
            }
        )
    return normalized


def _normalize_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for memory in memories:
        if not isinstance(memory, dict):
            continue
        content = str(memory.get("content", "")).strip()
        memory_type = str(memory.get("memory_type", "")).strip()
        if not content or memory_type not in {"profile", "episodic"}:
            continue
        normalized.append(
            {
                "schema_version": SCHEMA_VERSION,
                "memory_type": memory_type,
                "salience": _clean_score(memory.get("salience"), default=0.6),
                "recency": _clean_score(memory.get("recency"), default=0.8),
                "content": content,
                "source_event_title": str(memory.get("source_event_title", "")).strip(),
                "related_character_names": _clean_string_list(memory.get("related_character_names", [])),
                "emotion_valence": str(memory.get("emotion_valence", "")).strip(),
                "source_segments": _clean_string_list(memory.get("source_segments", [])),
            }
        )
    return normalized


def _clean_int_score(value: Any) -> int:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(score, 100))


async def _attach_memory_embeddings(
    model_adapter: ModelAdapter,
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not payloads:
        return payloads
    try:
        embedding_result = await model_adapter.embed([payload["content"] for payload in payloads])
    except Exception:
        return payloads

    enriched: list[dict[str, Any]] = []
    for payload, vector in zip(payloads, embedding_result.vectors, strict=False):
        next_payload = dict(payload)
        next_payload["embedding"] = vector
        enriched.append(next_payload)
    if len(enriched) < len(payloads):
        enriched.extend(payloads[len(enriched):])
    return enriched
