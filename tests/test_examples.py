from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


def test_yue_buqun_portrait_example_matches_schema() -> None:
    schema = json.loads((ROOT / "prompts/schemas/character_portrait.json").read_text(encoding="utf-8"))
    portrait = json.loads((ROOT / "examples/yue-buqun/portrait.json").read_text(encoding="utf-8"))

    errors = sorted(Draft202012Validator(schema).iter_errors(portrait), key=lambda item: list(item.path))

    assert errors == []


def test_yue_buqun_memory_example_stays_in_sync_with_portrait() -> None:
    portrait = json.loads((ROOT / "examples/yue-buqun/portrait.json").read_text(encoding="utf-8"))
    memories = json.loads((ROOT / "examples/yue-buqun/memories.json").read_text(encoding="utf-8"))

    portrait_lookup = {
        (item["memory_type"], item["content"]): item
        for item in portrait["memories"]
    }

    assert len(memories) == len(portrait["memories"])

    for record in memories:
        key = (record["memory_type"], record["content"])
        assert key in portrait_lookup
        assert record["schema_version"] == "0.2"
        assert record["project_id"] == "proj_demo_swordsman"
        assert record["character_id"] == "char_yue_buqun"
        assert record["source_segments"] == portrait_lookup[key]["source_segments"]
