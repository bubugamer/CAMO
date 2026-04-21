from __future__ import annotations

from camo.extraction.pass1 import CharacterMention, _aggregate_mentions


def test_aggregate_mentions_merges_alias_overlap() -> None:
    mentions = [
        CharacterMention(
            name="张三",
            aliases=["三哥"],
            titles=["张老板"],
            identities=[{"type": "occupation", "value": "merchant"}],
            description="商人",
            character_type="real_person",
            segment_id="seg_1",
            position=1,
        ),
        CharacterMention(
            name="三哥",
            aliases=["张三"],
            titles=[],
            identities=[{"type": "social_role", "value": "elder_brother"}],
            description="张家老三",
            character_type="real_person",
            segment_id="seg_2",
            position=2,
        ),
    ]

    aggregated = _aggregate_mentions(mentions=mentions, total_segments=2)

    assert len(aggregated) == 1
    payload = aggregated[0]["character_index"]
    assert payload["schema_version"] == "0.2"
    assert payload["character_type"] == "real_person"
    assert payload["name"] in {"三哥", "张三"}
    assert payload["description"] in {"商人", "张家老三"}
    assert set(payload["aliases"]) == {"三哥", "张三"} - {payload["name"]}
    assert payload["titles"] == ["张老板"]
    assert payload["first_appearance"] == "seg_1"
    assert payload["confidence"] == 1.0
    assert payload["source_segments"] == ["seg_1", "seg_2"]
    assert payload["identities"] == [
        {"type": "occupation", "value": "merchant"},
        {"type": "social_role", "value": "elder_brother"},
    ]
