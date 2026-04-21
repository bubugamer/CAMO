from __future__ import annotations

from camo.db.models import Character, TextSegment
from camo.extraction.pass2 import (
    _build_character_lookup,
    _build_memory_payloads,
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
            index_payload={"name": "岳不群", "aliases": ["岳先生"]},
        ),
        Character(
            character_id="char_linghu",
            project_id="proj_demo",
            index_payload={"name": "令狐冲", "aliases": []},
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
