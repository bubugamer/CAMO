from __future__ import annotations

from typing import Any

from camo.db.models import Character, Memory
from camo.models.adapter import ModelAdapter
from camo.prompts import load_json_schema, render_prompt


async def run_character_chat(
    *,
    model_adapter: ModelAdapter,
    character: Character,
    memories: list[Memory],
    user_message: str,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    selected_memories = select_chat_memories(memories, limit=6)
    prompt = render_prompt(
        "runtime/character_chat.jinja2",
        character_index=character.character_index,
        character_core=character.character_core or {},
        character_facet=character.character_facet or {},
        memories=[
            {
                "memory_id": memory.memory_id,
                "memory_type": memory.memory_type,
                "content": memory.content,
                "salience": memory.salience,
                "emotion_valence": memory.emotion_valence,
            }
            for memory in selected_memories
        ],
    )
    schema = load_json_schema("schemas/character_chat.json")
    result = await model_adapter.complete(
        messages=[
            {"role": "system", "content": prompt},
            *(history or []),
            {"role": "user", "content": user_message},
        ],
        task="runtime",
        json_schema=schema,
    )
    structured = result.structured or {}
    response = structured.get("response", {})
    reply = str(response.get("content", result.content)).strip()
    style_tags = [str(item).strip() for item in response.get("style_tags", []) if str(item).strip()]
    tone = ", ".join(style_tags) or str(
        character.character_core.get("communication_profile", {}).get("tone", "in-character")
        if character.character_core
        else "in-character"
    ).strip()
    return {
        "reply": reply,
        "tone": tone or "in-character",
        "style_tags": style_tags,
        "speaker": str(response.get("speaker", character.character_index.get("name", ""))).strip(),
        "reasoning_summary": str(structured.get("reasoning_summary", "")).strip(),
        "triggered_memories": structured.get("triggered_memories", []),
        "applied_rules": structured.get("applied_rules", []),
        "consistency_check": structured.get("consistency_check", {}),
        "memory_count": len(selected_memories),
    }


def select_chat_memories(memories: list[Memory], *, limit: int) -> list[Memory]:
    ordered = sorted(
        memories,
        key=lambda item: (
            0 if item.memory_type == "profile" else 1,
            -item.salience,
            -item.recency,
        ),
    )
    return ordered[:limit]
