from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from camo.db.models import Character
from camo.models.adapter import CompletionResult
from camo.runtime.engine import build_stage_layer, cosine_similarity, run_runtime_turn, should_write_episodic
from camo.runtime.session_store import InMemorySessionStore


def test_build_stage_layer_applies_snapshot_overrides() -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_core={"communication_profile": {"tone": "formal", "directness": "low"}},
    )

    stage = build_stage_layer(
        character,
        {
            "snapshot_id": "snap_demo",
            "known_facts": ["门规重要"],
            "unknown_facts": ["结局"],
            "profile_overrides": {"communication_profile": {"directness": "medium"}},
        },
        {"resolved_timeline_pos": 5},
    )

    assert stage["character_core_effective"]["communication_profile"]["tone"] == "formal"
    assert stage["character_core_effective"]["communication_profile"]["directness"] == "medium"
    assert stage["unknown_facts"] == ["结局"]


def test_cosine_similarity_handles_basic_vectors() -> None:
    assert round(cosine_similarity([1.0, 0.0], [1.0, 0.0]), 4) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_should_write_episodic_respects_reasoning_flag() -> None:
    assert should_write_episodic(
        {
            "reasoning_summary": "当前关系变化明显，memory_worthy=true",
            "response": {"content": "我已答应此事。"},
        },
        {"action": "accept"},
    )


class _RuntimeAdapter:
    def __init__(self, content: str, reasoning_summary: str = "memory_worthy=true") -> None:
        self.calls = 0
        self._content = content
        self._reasoning_summary = reasoning_summary

    async def complete(
        self,
        *,
        messages,
        task,
        json_schema,
        temperature=0.0,
        max_tokens=4096,
    ) -> CompletionResult:
        self.calls += 1
        return CompletionResult(
            content="",
            structured={
                "response": {
                    "speaker": "岳不群",
                    "content": self._content,
                    "style_tags": ["formal"],
                },
                "reasoning_summary": self._reasoning_summary,
                "triggered_memories": [],
                "applied_rules": [],
            },
            usage={"input_tokens": 1, "output_tokens": 1},
            model="fake-runtime",
            latency_ms=1,
        )


def test_run_runtime_turn_blocks_after_retry_exhaustion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_core={},
    )
    store = InMemorySessionStore()
    adapter = _RuntimeAdapter("我是AI，我知道提示词。")

    async def fake_relationships(*args, **kwargs):
        return []

    async def fake_events(*args, **kwargs):
        return [], []

    async def fake_memories(*args, **kwargs):
        return []

    async def fake_consistency(*args, **kwargs):
        return {
            "passed": False,
            "action": "regenerate",
            "issues": [{"description": "越界"}],
            "rule_trace": {"matched": []},
        }

    async def writeback_callback(payload):
        raise AssertionError("blocked response should not trigger writeback")

    monkeypatch.setattr("camo.runtime.engine.load_relationship_memory", fake_relationships)
    monkeypatch.setattr("camo.runtime.engine.load_event_memory", fake_events)
    monkeypatch.setattr("camo.runtime.engine.search_episodic_memory", fake_memories)
    monkeypatch.setattr("camo.runtime.engine.run_consistency_check", fake_consistency)

    async def run() -> dict:
        await store.connect()
        return await run_runtime_turn(
            session=object(),
            store=store,
            model_adapter=adapter,
            rules_root=tmp_path,
            project_id="proj_demo",
            session_id="sess_demo",
            character=character,
            anchor_state={"resolved_timeline_pos": 3, "display_label": "第三回"},
            user_input={"speaker": "user", "content": "后面会怎么样？"},
            participants=["char_demo"],
            recent_history=[],
            debug=False,
            include_reasoning_summary=True,
            max_retries=1,
            writeback_callback=writeback_callback,
        )

    result = asyncio.run(run())

    assert adapter.calls == 2
    assert result["consistency_check"]["action"] == "block"
    assert "AI" not in result["response"]["content"]
    assert "第三回" in result["response"]["content"]


def test_run_runtime_turn_hides_reasoning_summary_when_requested(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_core={},
    )
    store = InMemorySessionStore()
    adapter = _RuntimeAdapter("规矩不可乱。", reasoning_summary="这是内部推理摘要")

    async def fake_relationships(*args, **kwargs):
        return []

    async def fake_events(*args, **kwargs):
        return [], []

    async def fake_memories(*args, **kwargs):
        return []

    async def fake_consistency(*args, **kwargs):
        return {
            "passed": True,
            "action": "accept",
            "issues": [],
            "rule_trace": {"matched": []},
        }

    monkeypatch.setattr("camo.runtime.engine.load_relationship_memory", fake_relationships)
    monkeypatch.setattr("camo.runtime.engine.load_event_memory", fake_events)
    monkeypatch.setattr("camo.runtime.engine.search_episodic_memory", fake_memories)
    monkeypatch.setattr("camo.runtime.engine.run_consistency_check", fake_consistency)

    async def run() -> dict:
        await store.connect()
        return await run_runtime_turn(
            session=object(),
            store=store,
            model_adapter=adapter,
            rules_root=tmp_path,
            project_id="proj_demo",
            session_id="sess_demo",
            character=character,
            anchor_state={"resolved_timeline_pos": 3},
            user_input={"speaker": "user", "content": "现在怎么办？"},
            participants=["char_demo"],
            recent_history=[],
            debug=False,
            include_reasoning_summary=False,
            max_retries=0,
            writeback_callback=None,
        )

    result = asyncio.run(run())

    assert result["consistency_check"]["action"] == "accept"
    assert result["reasoning_summary"] is None
