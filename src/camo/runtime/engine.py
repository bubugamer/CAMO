from __future__ import annotations

import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from camo.core.patching import deep_merge
from camo.db.models import Character
from camo.db.queries.events import list_events_for_character
from camo.db.queries.memories import list_memories_for_character
from camo.db.queries.relationships import list_relationships_for_character
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt
from camo.runtime.anchors import load_active_snapshot
from camo.runtime.consistency import run_consistency_check
from camo.runtime.session_store import SessionStore


async def run_runtime_turn(
    *,
    session: AsyncSession,
    store: SessionStore,
    model_adapter: ModelAdapter,
    rules_root,
    project_id: str,
    session_id: str,
    character: Character,
    anchor_state: dict[str, Any],
    user_input: dict[str, Any],
    participants: list[str],
    recent_history: list[dict[str, Any]],
    debug: bool,
    include_reasoning_summary: bool,
    max_retries: int,
    writeback_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    snapshot = load_active_snapshot(character, int(anchor_state["resolved_timeline_pos"]))
    fixed_identity = build_fixed_identity_layer(character)
    current_stage = build_stage_layer(character, snapshot, anchor_state)

    relationships = await load_relationship_memory(
        session,
        project_id=project_id,
        character_id=character.character_id,
        anchor_state=anchor_state,
        participants=participants,
    )
    events, future_events = await load_event_memory(
        session,
        project_id=project_id,
        character_id=character.character_id,
        anchor_state=anchor_state,
    )
    episodic = await search_episodic_memory(
        session,
        model_adapter=model_adapter,
        project_id=project_id,
        character_id=character.character_id,
        anchor_state=anchor_state,
        query_text=user_input["content"],
    )
    working_memory = await store.load_working_memory(session_id)

    retrieved_memories = {
        "relationships": relationships,
        "events": events,
        "episodic_memories": episodic,
    }
    context_window = {
        "refusal_rules": build_refusal_rule_layer(character, anchor_state),
        "fixed_identity": fixed_identity,
        "current_stage": current_stage,
        "retrieved_memories": retrieved_memories,
        "working_memory": working_memory,
        "recent_history": recent_history,
    }

    schema = load_json_schema("schemas/runtime_turn.json")
    retry_message: dict[str, str] | None = None
    final_check: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None

    for attempt in range(max_retries + 1):
        prompt = render_prompt(
            "runtime/turn.jinja2",
            **context_window,
        )
        messages = [{"role": "system", "content": prompt}]
        if retry_message is not None:
            messages.append(retry_message)
        result = await model_adapter.complete(
            messages=[
                *messages,
                {"role": "user", "content": user_input["content"]},
            ],
            task="runtime",
            json_schema=schema,
        )
        structured = result.structured or {}
        response = structured.get("response", {})
        result_payload = {
            "response": {
                "speaker": str(response.get("speaker", character.character_index.get("name", ""))).strip(),
                "content": str(response.get("content", result.content)).strip(),
                "style_tags": [
                    str(item).strip()
                    for item in response.get("style_tags", [])
                    if str(item).strip()
                ],
            },
            "reasoning_summary": str(structured.get("reasoning_summary", "")).strip(),
            "triggered_memories": [
                item for item in structured.get("triggered_memories", []) if isinstance(item, dict)
            ],
            "applied_rules": [
                item for item in structured.get("applied_rules", []) if isinstance(item, dict)
            ],
        }

        final_check = await run_consistency_check(
            model_adapter=model_adapter,
            character=character,
            anchor_state=anchor_state,
            fixed_identity=fixed_identity,
            current_stage=current_stage,
            retrieval_summary={
                "relationships": relationships,
                "events": events,
                "future_events": future_events,
                "episodic_memories": episodic,
            },
            user_input=user_input,
            runtime_response=result_payload["response"],
            rules_root=rules_root,
        )
        if final_check["action"] != "regenerate" or attempt >= max_retries:
            break
        retry_message = {
            "role": "system",
            "content": _build_retry_guidance(final_check["issues"]),
        }

    assert result_payload is not None
    assert final_check is not None

    if final_check["action"] == "regenerate":
        final_check = {
            **final_check,
            "passed": False,
            "action": "block",
        }
        result_payload["response"] = build_block_response(
            character=character,
            anchor_state=anchor_state,
        )

    await store.append_working_memory(
        session_id,
        {
            "speaker": user_input.get("speaker", "user"),
            "content": user_input["content"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    await store.append_working_memory(
        session_id,
        {
            "speaker": result_payload["response"]["speaker"],
            "content": result_payload["response"]["content"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    if writeback_callback is not None and should_write_episodic(result_payload, final_check):
        await writeback_callback(
            {
                "project_id": project_id,
                "character_id": character.character_id,
                "participants": participants,
                "anchor_state": anchor_state,
                "response": result_payload["response"],
                "reasoning_summary": result_payload["reasoning_summary"],
            }
        )

    payload = {
        "session_id": session_id,
        "anchor_state": anchor_state,
        "response": result_payload["response"],
        "reasoning_summary": result_payload["reasoning_summary"] if include_reasoning_summary else None,
        "triggered_memories": result_payload["triggered_memories"],
        "applied_rules": result_payload["applied_rules"],
        "consistency_check": {
            "passed": final_check["passed"],
            "action": final_check["action"],
            "issues": final_check["issues"],
        },
    }
    if debug:
        payload["anchor_trace"] = {"anchor_state": anchor_state, "snapshot_id": snapshot.get("snapshot_id") if snapshot else None}
        payload["context_window"] = context_window
        payload["retrieval_trace"] = {
            "relationship_count": len(relationships),
            "event_count": len(events),
            "episodic_count": len(episodic),
            "working_memory_count": len(working_memory),
        }
        payload["rule_trace"] = final_check.get("rule_trace")
    return payload


def build_fixed_identity_layer(character: Character) -> dict[str, Any]:
    return {
        "character_index": deepcopy(character.character_index),
        "character_core": deepcopy(character.character_core or {}),
        "biographical_notes": deepcopy((character.character_facet or {}).get("biographical_notes", {})),
    }


def build_stage_layer(
    character: Character,
    snapshot: dict[str, Any] | None,
    anchor_state: dict[str, Any],
) -> dict[str, Any]:
    character_core = deepcopy(character.character_core or {})
    if snapshot is not None:
        profile_overrides = snapshot.get("profile_overrides", {})
        if isinstance(profile_overrides, dict):
            character_core = deep_merge(character_core, profile_overrides)

    return {
        "anchor_state": deepcopy(anchor_state),
        "snapshot": deepcopy(snapshot) if snapshot is not None else None,
        "character_core_effective": character_core,
        "known_facts": deepcopy((snapshot or {}).get("known_facts", [])),
        "unknown_facts": deepcopy((snapshot or {}).get("unknown_facts", [])),
    }


def build_refusal_rule_layer(character: Character, anchor_state: dict[str, Any]) -> dict[str, Any]:
    forbidden = (
        character.character_core.get("constraint_profile", {}).get("forbidden_behaviors", [])
        if character.character_core
        else []
    )
    return {
        "anchor_summary": anchor_state.get("summary", ""),
        "default_policy": "保持角色口吻，避免透露锚点之后的剧情、时代外概念和作品外设定。",
        "forbidden_behaviors": deepcopy(forbidden),
    }


async def load_relationship_memory(
    session: AsyncSession,
    *,
    project_id: str,
    character_id: str,
    anchor_state: dict[str, Any],
    participants: list[str],
) -> list[dict[str, Any]]:
    cutoff = int(anchor_state["resolved_timeline_pos"])
    relationships = await list_relationships_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    participant_set = {item for item in participants if item and item != character_id}
    loaded: list[dict[str, Any]] = []
    for relationship in relationships:
        if participant_set and relationship.target_id not in participant_set and relationship.source_id not in participant_set:
            continue
        active_state = relationship.public_state
        active_hidden_state = relationship.hidden_state
        timeline = relationship.timeline or []
        for item in timeline:
            effective = item.get("effective_range", {})
            start = int(effective.get("start_timeline_pos", 1))
            end = int(effective.get("end_timeline_pos", start))
            if start <= cutoff <= end:
                active_state = item.get("public_state") or active_state
                active_hidden_state = item.get("hidden_state") if "hidden_state" in item else active_hidden_state
        loaded.append(
            {
                "relationship_id": relationship.relationship_id,
                "target_character_id": relationship.target_id,
                "relation_category": relationship.relation_category,
                "relation_subtype": relationship.relation_subtype,
                "public_state": deepcopy(active_state),
                "hidden_state": deepcopy(active_hidden_state),
                "confidence": relationship.confidence,
            }
        )
    return loaded


async def load_event_memory(
    session: AsyncSession,
    *,
    project_id: str,
    character_id: str,
    anchor_state: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cutoff = int(anchor_state["resolved_timeline_pos"])
    events = await list_events_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    prior: list[dict[str, Any]] = []
    future: list[dict[str, Any]] = []
    for event in events:
        payload = {
            "event_id": event.event_id,
            "title": event.title,
            "description": event.description,
            "timeline_pos": event.timeline_pos,
            "location": event.location,
            "emotion_valence": event.emotion_valence,
        }
        if event.timeline_pos is None or event.timeline_pos <= cutoff:
            prior.append(payload)
        else:
            future.append(payload)
    return prior[-8:], future[:8]


async def search_episodic_memory(
    session: AsyncSession,
    *,
    model_adapter: ModelAdapter,
    project_id: str,
    character_id: str,
    anchor_state: dict[str, Any],
    query_text: str,
    limit: int = 6,
) -> list[dict[str, Any]]:
    cutoff = int(anchor_state["resolved_timeline_pos"])
    memories = await list_memories_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    events = await list_events_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    event_timeline = {event.event_id: event.timeline_pos for event in events}

    try:
        embedding_result = await model_adapter.embed([query_text])
        query_vector = embedding_result.vectors[0] if embedding_result.vectors else []
    except Exception:
        query_vector = []

    candidates: list[tuple[float, dict[str, Any]]] = []
    for memory in memories:
        memory_timeline = event_timeline.get(memory.source_event_id)
        if memory.memory_type == "episodic" and memory_timeline is not None and memory_timeline > cutoff:
            continue
        similarity = cosine_similarity(query_vector, memory.embedding or [])
        score = memory.salience * 0.4 + memory.recency * 0.2 + similarity * 0.4
        candidates.append(
            (
                score,
                {
                    "memory_id": memory.memory_id,
                    "memory_type": memory.memory_type,
                    "content": memory.content,
                    "salience": memory.salience,
                    "recency": memory.recency,
                    "emotion_valence": memory.emotion_valence,
                    "similarity": round(similarity, 4),
                },
            )
        )

    ordered = sorted(candidates, key=lambda item: item[0], reverse=True)
    return [item for _, item in ordered[:limit]]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, numerator / (left_norm * right_norm)))


def should_write_episodic(result_payload: dict[str, Any], consistency_check: dict[str, Any]) -> bool:
    if consistency_check.get("action") not in {"accept", "warn"}:
        return False
    reasoning = str(result_payload.get("reasoning_summary", "")).lower()
    content = str(result_payload.get("response", {}).get("content", "")).strip()
    if "memory_worthy=true" in reasoning:
        return True
    return any(keyword in content for keyword in ("答应", "承诺", "决意", "冲突", "隐瞒", "背叛"))


def _build_retry_guidance(issues: list[dict[str, Any]]) -> str:
    fragments = [str(item.get("description", "")).strip() for item in issues if str(item.get("description", "")).strip()]
    guidance = "；".join(fragments[:4]) or "上一次回复存在一致性问题。"
    return f"请重新生成回复，并避免以下问题：{guidance}"


def build_block_response(*, character: Character, anchor_state: dict[str, Any]) -> dict[str, Any]:
    display_label = str(anchor_state.get("display_label", "")).strip()
    summary = str(anchor_state.get("summary", "")).strip()
    fragments = ["此事我眼下不便断言。"]
    if display_label:
        fragments.append(f"依我如今所见，所知不过止于{display_label}。")
    elif summary:
        fragments.append(f"依我此刻所知，不过是{summary}。")
    fragments.append("若再多言，反倒容易失了分寸。")
    return {
        "speaker": str(character.character_index.get("name", "")).strip(),
        "content": "".join(fragments),
        "style_tags": ["guarded", "bounded"],
    }
