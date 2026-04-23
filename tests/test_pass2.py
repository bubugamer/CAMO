from __future__ import annotations

from camo.db.models import Character, TextSegment
from camo.extraction.pass2 import (
    _build_character_lookup,
    _build_relationship_payloads,
    _build_memory_payloads,
    _normalize_portrait_payload,
    select_character_evidence,
)


def test_select_character_evidence_matches_and_samples_segments() -> None:
    segments = [
        TextSegment(
            segment_id=f"seg_{index}",
            source_id="src_demo",
            position=index,
            chapter=None,
            round=None,
            content=f"这一段提到岳不群第{index}次。" if index in {1, 3, 5, 7} else "这一段无关。",
            raw_offset=index * 10,
            char_count=20,
            segment_metadata={},
        )
        for index in range(1, 9)
    ]

    evidence = select_character_evidence(segments, keywords=["岳不群"], max_segments=3, excerpt_chars=40)

    assert len(evidence) == 3
    assert evidence[0].segment_id == "seg_1"
    assert evidence[-1].segment_id == "seg_7"
    assert all("岳不群" in item.excerpt for item in evidence)


def test_build_memory_payloads_maps_related_character_names() -> None:
    characters = [
        Character(
            character_id="char_yue",
            project_id="proj_demo",
            character_index={"name": "岳不群", "aliases": ["岳先生"]},
        ),
        Character(
            character_id="char_linghu",
            project_id="proj_demo",
            character_index={"name": "令狐冲", "aliases": []},
        ),
    ]
    lookup = _build_character_lookup(characters)

    payloads = _build_memory_payloads(
        project_id="proj_demo",
        character_id="char_yue",
        extracted_memories=[
            {
                "schema_version": "0.2",
                "memory_type": "profile",
                "content": "他重视华山派门规与自身名望。",
                "salience": 0.9,
                "recency": 0.4,
                "emotion_valence": "mixed",
                "source_segments": ["seg_1"],
                "related_character_names": ["令狐冲", "陌生人"],
                "source_event_title": "训诫门人",
            }
        ],
        name_lookup=lookup,
        event_title_map={"训诫门人": "evt_demo"},
    )

    assert len(payloads) == 1
    payload = payloads[0]
    assert payload["schema_version"] == "0.2"
    assert payload["memory_type"] == "profile"
    assert payload["related_character_ids"] == ["char_linghu"]
    assert payload["source_event_id"] == "evt_demo"


def test_normalize_portrait_payload_builds_snapshots_relationships_and_timeline_positions() -> None:
    segment_lookup = {
        "seg_1": TextSegment(
            segment_id="seg_1",
            source_id="src_demo",
            position=10,
            chapter="第一回",
            round=None,
            content="岳不群初次训诫弟子。",
            raw_offset=0,
            char_count=10,
            segment_metadata={"timeline_pos": 2},
        ),
        "seg_2": TextSegment(
            segment_id="seg_2",
            source_id="src_demo",
            position=20,
            chapter="第二回",
            round=None,
            content="他与令狐冲关系开始紧张。",
            raw_offset=20,
            char_count=14,
            segment_metadata={"timeline_pos": 5},
        ),
    }

    normalized = _normalize_portrait_payload(
        {
            "character_core": {},
            "character_facet": {
                "biographical_notes": {},
                "evidence_map": {},
                "temporal_snapshots": [
                    {
                        "period_label": "后期猜疑",
                        "source_segments": ["seg_2"],
                        "display_hint": {"primary": "后期猜疑", "secondary": "华山内部分裂"},
                        "stage_summary": "对亲近弟子也愈发不信任。",
                        "known_facts": ["开始公开施压"],
                        "unknown_facts": ["真实底线"],
                        "profile_overrides": {"communication_profile": {"tone": "aggressive"}},
                        "notes": "对关系的控制欲明显增强。",
                    },
                    {
                        "period_label": "早期师门秩序",
                        "source_segments": ["seg_1"],
                        "display_hint": {"primary": "早期秩序", "secondary": ""},
                        "stage_summary": "仍以门规和体面为先。",
                        "known_facts": ["强调规矩"],
                        "unknown_facts": [],
                        "profile_overrides": {},
                        "notes": "主要以师长姿态出现。",
                    },
                ],
            },
            "relationships": [
                {
                    "target_name": "令狐冲",
                    "relation_category": "mentorship",
                    "relation_subtype": "master_disciple",
                    "public_state": {"strength": 85, "stance": "positive", "notes": "名义上仍是师徒"},
                    "hidden_state": {"strength": 35, "stance": "negative", "notes": "逐渐生疑"},
                    "timeline": [
                        {
                            "period_label": "早期师门秩序",
                            "public_state": {"strength": 90, "stance": "positive", "notes": "公开维护师徒名分"},
                            "hidden_state": None,
                            "source_segments": ["seg_1"],
                        },
                        {
                            "public_state": {"strength": 40, "stance": "negative", "notes": "转为压制"},
                            "hidden_state": {"strength": 75, "stance": "negative", "notes": "防备更深"},
                            "source_segments": ["seg_2"],
                        },
                    ],
                    "source_segments": ["seg_1", "seg_2"],
                    "confidence": 0.88,
                }
            ],
            "events": [
                {
                    "title": "训诫弟子",
                    "description": "以门规约束弟子。",
                    "participant_names": ["令狐冲"],
                    "location": "华山正堂",
                    "emotion_valence": "mixed",
                    "source_segments": ["seg_1"],
                }
            ],
            "memories": [],
        },
        source_ids=["src_demo"],
        character_id="char_yue",
        segment_lookup=segment_lookup,
    )

    snapshots = normalized["character_facet"]["temporal_snapshots"]
    assert [item["period_label"] for item in snapshots] == ["早期师门秩序", "后期猜疑"]
    assert snapshots[0]["activation_range"] == {"start_timeline_pos": 2, "end_timeline_pos": 2}
    assert snapshots[1]["activation_range"] == {"start_timeline_pos": 5, "end_timeline_pos": 5}

    relationship = normalized["relationships"][0]
    assert relationship["timeline"][0]["snapshot_id"] == snapshots[0]["snapshot_id"]
    assert relationship["timeline"][0]["effective_range"] == {"start_timeline_pos": 2, "end_timeline_pos": 2}
    assert relationship["timeline"][1]["snapshot_id"] == snapshots[1]["snapshot_id"]
    assert relationship["timeline"][1]["effective_range"] == {"start_timeline_pos": 5, "end_timeline_pos": 5}
    assert relationship["hidden_state"]["stance"] == "negative"

    assert normalized["events"][0]["timeline_pos"] == 2


def test_build_relationship_payloads_maps_known_targets_and_uses_category_in_identity() -> None:
    payloads = _build_relationship_payloads(
        project_id="proj_demo",
        character_id="char_yue",
        extracted_relationships=[
            {
                "schema_version": "0.2",
                "target_name": "令狐冲",
                "relation_category": "mentorship",
                "relation_subtype": "master_disciple",
                "public_state": {"strength": 80, "stance": "positive", "notes": "仍是弟子"},
                "hidden_state": {"strength": 20, "stance": "negative", "notes": "暗中不满"},
                "timeline": [],
                "source_segments": ["seg_1"],
                "confidence": 0.7,
            },
            {
                "schema_version": "0.2",
                "target_name": "令狐冲",
                "relation_category": "alliance",
                "relation_subtype": "master_disciple",
                "public_state": {"strength": 50, "stance": "neutral", "notes": ""},
                "hidden_state": None,
                "timeline": [],
                "source_segments": ["seg_2"],
                "confidence": 0.4,
            },
            {
                "schema_version": "0.2",
                "target_name": "陌生人",
                "relation_category": "alliance",
                "relation_subtype": "temporary",
                "public_state": {"strength": 50, "stance": "neutral", "notes": ""},
                "hidden_state": None,
                "timeline": [],
                "source_segments": ["seg_3"],
                "confidence": 0.4,
            },
        ],
        name_lookup={"令狐冲": "char_linghu"},
    )

    assert len(payloads) == 2
    assert payloads[0]["target_id"] == "char_linghu"
    assert payloads[0]["relation_category"] == "mentorship"
    assert payloads[0]["relationship_id"].startswith("rel_")
    assert payloads[0]["relationship_id"] != payloads[1]["relationship_id"]
