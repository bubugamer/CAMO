from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha1
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Character, Event, Memory, TextSegment
from camo.db.queries.characters import ensure_character_shell, list_characters, save_character_portrait
from camo.db.queries.events import upsert_events
from camo.db.queries.memories import replace_memories_for_character
from camo.db.queries.texts import list_text_segments_for_source
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt

SCHEMA_VERSION = "0.2"


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
) -> tuple[Character, list[Event], list[Memory], int, list[str]]:
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

    schema = load_json_schema("schemas/character_portrait.json")
    prompt = render_prompt(
        "extraction/character_portrait.jinja2",
        character_name=name,
        aliases=resolved_aliases,
        known_character_list=[
            {
                "character_id": item.character_id,
                "name": item.index_payload.get("name", ""),
                "aliases": item.index_payload.get("aliases", []),
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
    normalized_payload = _normalize_portrait_payload(structured, source_id=source_id)
    core = normalized_payload["core"]
    facet = normalized_payload["facet"]
    await save_character_portrait(session, character, core=core, facet=facet)

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
    stored_memories = await replace_memories_for_character(
        session,
        character_id=character.character_id,
        memory_types=["profile", "episodic"],
        memories=memory_payloads,
    )
    await session.refresh(character)
    return character, stored_events, stored_memories, len(evidence), [item.segment_id for item in evidence]


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
        payload = character.index_payload
        for name in [payload.get("name", ""), *payload.get("aliases", [])]:
            normalized = _normalize_name(str(name))
            if normalized:
                lookup[normalized] = character.character_id
    return lookup


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


def _normalize_portrait_payload(payload: dict[str, Any], *, source_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "core": _normalize_core(payload.get("core", {})),
        "facet": _normalize_facet(payload.get("facet", {}), source_id=source_id),
        "events": _normalize_events(payload.get("events", [])),
        "memories": _normalize_memories(payload.get("memories", [])),
    }


def _normalize_core(core: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "trait_profile": {
            "openness": _clean_int_score(core.get("trait_profile", {}).get("openness")),
            "conscientiousness": _clean_int_score(core.get("trait_profile", {}).get("conscientiousness")),
            "extraversion": _clean_int_score(core.get("trait_profile", {}).get("extraversion")),
            "agreeableness": _clean_int_score(core.get("trait_profile", {}).get("agreeableness")),
            "neuroticism": _clean_int_score(core.get("trait_profile", {}).get("neuroticism")),
        },
        "motivation_profile": {
            "primary": _clean_string_list(core.get("motivation_profile", {}).get("primary", [])),
            "secondary": _clean_string_list(core.get("motivation_profile", {}).get("secondary", [])),
            "suppressed": _clean_string_list(core.get("motivation_profile", {}).get("suppressed", [])),
        },
        "behavior_profile": {
            "conflict_style": str(core.get("behavior_profile", {}).get("conflict_style", "")).strip(),
            "risk_preference": str(core.get("behavior_profile", {}).get("risk_preference", "")).strip(),
            "decision_style": str(core.get("behavior_profile", {}).get("decision_style", "")).strip(),
            "dominance_style": str(core.get("behavior_profile", {}).get("dominance_style", "")).strip(),
        },
        "communication_profile": {
            "tone": str(core.get("communication_profile", {}).get("tone", "")).strip(),
            "directness": str(core.get("communication_profile", {}).get("directness", "")).strip(),
            "emotional_expressiveness": str(
                core.get("communication_profile", {}).get("emotional_expressiveness", "")
            ).strip(),
            "verbosity": str(core.get("communication_profile", {}).get("verbosity", "")).strip(),
            "politeness": str(core.get("communication_profile", {}).get("politeness", "")).strip(),
        },
        "constraint_profile": {
            "knowledge_scope": str(core.get("constraint_profile", {}).get("knowledge_scope", "")).strip(),
            "role_consistency": str(core.get("constraint_profile", {}).get("role_consistency", "")).strip(),
            "forbidden_behaviors": [
                {
                    "namespace": str(item.get("namespace", "")).strip(),
                    "tag": str(item.get("tag", "")).strip(),
                    "description": str(item.get("description", "")).strip(),
                }
                for item in core.get("constraint_profile", {}).get("forbidden_behaviors", [])
                if isinstance(item, dict)
                and str(item.get("namespace", "")).strip()
                and str(item.get("tag", "")).strip()
                and str(item.get("description", "")).strip()
            ],
        },
    }


def _normalize_facet(facet: dict[str, Any], *, source_id: str) -> dict[str, Any]:
    evidence_map: dict[str, list[dict[str, Any]]] = {}
    for field_path, entries in (facet.get("evidence_map", {}) or {}).items():
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
            "appearance": str(facet.get("biographical_notes", {}).get("appearance", "")).strip(),
            "backstory": str(facet.get("biographical_notes", {}).get("backstory", "")).strip(),
            "signature_habits": _clean_string_list(
                facet.get("biographical_notes", {}).get("signature_habits", [])
            ),
            "catchphrases": _clean_string_list(facet.get("biographical_notes", {}).get("catchphrases", [])),
        },
        "temporal_snapshots": [
            {
                "period_label": str(item.get("period_label", "")).strip(),
                "period_source": _clean_string_list(item.get("period_source", [])),
                "changes": item.get("changes", {}) if isinstance(item.get("changes"), dict) else {},
                "notes": str(item.get("notes", "")).strip(),
            }
            for item in facet.get("temporal_snapshots", [])
            if isinstance(item, dict) and str(item.get("period_label", "")).strip()
        ],
        "extraction_meta": {
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "source_texts": [source_id],
            "reviewer_status": str(facet.get("extraction_meta", {}).get("reviewer_status", "")).strip()
            or "unreviewed",
            "reviewer_notes": str(facet.get("extraction_meta", {}).get("reviewer_notes", "")).strip(),
            "schema_version": SCHEMA_VERSION,
        },
    }


def _normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            continue
        title = str(event.get("title", "")).strip()
        if not title:
            continue
        normalized.append(
            {
                "schema_version": SCHEMA_VERSION,
                "title": title,
                "description": str(event.get("description", "")).strip(),
                "timeline_pos": event.get("timeline_pos") if isinstance(event.get("timeline_pos"), int) else index,
                "participant_names": _clean_string_list(event.get("participant_names", [])),
                "location": str(event.get("location", "")).strip(),
                "emotion_valence": str(event.get("emotion_valence", "")).strip(),
                "source_segments": _clean_string_list(event.get("source_segments", [])),
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
