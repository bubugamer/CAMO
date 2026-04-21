from __future__ import annotations

import asyncio

from camo.db.models import Character
from camo.db.models import Memory
from camo.models.adapter import CompletionResult
from camo.runtime.chat import run_character_chat, select_chat_memories


class FakeChatAdapter:
    async def complete(
        self,
        *,
        messages,
        task,
        json_schema,
        temperature=0.0,
        max_tokens=4096,
    ) -> CompletionResult:
        return CompletionResult(
            content="",
            structured={
                "response": {
                    "speaker": "岳不群",
                    "content": "冲儿，此事不可操之过急。",
                    "style_tags": ["formal", "guarded"],
                },
                "reasoning_summary": "保持掌门人的克制口吻。",
                "triggered_memories": [{"memory_id": "mem_2", "reason": "涉及门规"}],
                "applied_rules": [{"namespace": "meta", "tag": "break_character"}],
                "consistency_check": {"passed": True, "issues": []},
            },
            usage={"input_tokens": 10, "output_tokens": 8},
            model="fake-runtime",
            latency_ms=3,
        )


def test_select_chat_memories_prioritizes_profile_then_salience() -> None:
    memories = [
        Memory(
            memory_id="mem_1",
            character_id="char_demo",
            project_id="proj_demo",
            memory_type="episodic",
            salience=0.7,
            recency=0.6,
            content="episodic medium",
            related_character_ids=[],
            source_segments=[],
        ),
        Memory(
            memory_id="mem_2",
            character_id="char_demo",
            project_id="proj_demo",
            memory_type="profile",
            salience=0.4,
            recency=0.4,
            content="profile low",
            related_character_ids=[],
            source_segments=[],
        ),
        Memory(
            memory_id="mem_3",
            character_id="char_demo",
            project_id="proj_demo",
            memory_type="episodic",
            salience=0.9,
            recency=0.8,
            content="episodic high",
            related_character_ids=[],
            source_segments=[],
        ),
    ]

    selected = select_chat_memories(memories, limit=2)

    assert [item.memory_id for item in selected] == ["mem_2", "mem_3"]


def test_run_character_chat_reads_runtime_schema() -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        index_payload={"name": "岳不群"},
        core={
            "communication_profile": {
                "tone": "formal",
            }
        },
    )
    memories = [
        Memory(
            memory_id="mem_2",
            character_id="char_demo",
            project_id="proj_demo",
            memory_type="profile",
            salience=0.9,
            recency=0.6,
            content="门规极重。",
            related_character_ids=[],
            source_segments=[],
        )
    ]

    result = asyncio.run(
        run_character_chat(
            model_adapter=FakeChatAdapter(),
            character=character,
            memories=memories,
            user_message="师父怎么看？",
        )
    )

    assert result["reply"] == "冲儿，此事不可操之过急。"
    assert result["tone"] == "formal, guarded"
    assert result["style_tags"] == ["formal", "guarded"]
    assert result["speaker"] == "岳不群"
    assert result["reasoning_summary"] == "保持掌门人的克制口吻。"
    assert result["memory_count"] == 1
