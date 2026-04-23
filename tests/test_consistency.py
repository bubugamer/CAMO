from __future__ import annotations

import asyncio
from pathlib import Path

from camo.db.models import Character
from camo.models.adapter import ProviderConfigurationError
from camo.runtime.consistency import resolve_action, run_rule_engine


def test_rule_engine_catches_meta_break_character(tmp_path: Path) -> None:
    rules_root = tmp_path / "rules"
    (rules_root / "meta").mkdir(parents=True)
    (rules_root / "setting").mkdir(parents=True)
    (rules_root / "plot").mkdir(parents=True)
    (rules_root / "meta" / "break_character.txt").write_text("AI\n提示词\n", encoding="utf-8")

    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_core={"constraint_profile": {"forbidden_behaviors": []}},
    )
    issues, trace = run_rule_engine(
        character=character,
        anchor_state={"resolved_timeline_pos": 3},
        current_stage={"unknown_facts": []},
        retrieval_summary={"future_events": []},
        reply_text="我是AI，我知道提示词。",
        rules_root=rules_root,
    )

    assert issues
    assert trace["matched"][0]["rule"] == "meta.break_character"
    assert resolve_action(issues) == "regenerate"


def test_judge_unavailable_is_reported_without_escalating_action(tmp_path: Path) -> None:
    rules_root = tmp_path / "rules"
    (rules_root / "meta").mkdir(parents=True)
    (rules_root / "setting").mkdir(parents=True)
    (rules_root / "plot").mkdir(parents=True)

    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_core={"constraint_profile": {"forbidden_behaviors": []}},
    )

    class JudgeUnavailableAdapter:
        async def complete(self, *args, **kwargs):
            raise ProviderConfigurationError("judge provider missing")

    async def run() -> dict:
        from camo.runtime.consistency import run_consistency_check

        return await run_consistency_check(
            model_adapter=JudgeUnavailableAdapter(),
            character=character,
            anchor_state={"resolved_timeline_pos": 3},
            fixed_identity={"character_index": {"name": "岳不群"}},
            current_stage={"unknown_facts": []},
            retrieval_summary={"future_events": []},
            user_input={"speaker": "user", "content": "你怎么看"},
            runtime_response={"speaker": "岳不群", "content": "此事不便多言。"},
            rules_root=rules_root,
        )

    result = asyncio.run(run())

    assert result["action"] == "accept"
    assert result["passed"] is True
    assert result["issues"][0]["evidence_rule_id"] == "system.judge_unavailable"
