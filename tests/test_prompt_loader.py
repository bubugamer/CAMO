from __future__ import annotations

from camo.prompts.loader import get_prompts_root, load_json_schema


def test_prompt_loader_finds_repo_prompts() -> None:
    schema = load_json_schema("schemas/character_index.json")

    assert get_prompts_root().name == "prompts"
    assert schema["properties"]["schema_version"]["const"] == "0.2"
