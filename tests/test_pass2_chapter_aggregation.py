from __future__ import annotations

from camo.db.models import TextSegment
from camo.extraction.pass2 import SegmentEvidence, group_evidence_by_chapter, merge_chapter_payloads


def test_group_evidence_by_chapter_respects_per_chapter_sampling() -> None:
    segments = {
        f"seg_{index}": TextSegment(
            segment_id=f"seg_{index}",
            source_id="src_demo",
            position=index,
            chapter="第一回" if index <= 3 else "第二回",
            round=None,
            content=f"第{index}段提到岳不群。",
            raw_offset=index * 10,
            char_count=20,
            segment_metadata={"timeline_pos": index},
        )
        for index in range(1, 7)
    }
    evidence = [
        SegmentEvidence(segment_id=segment.segment_id, position=segment.position, chapter=segment.chapter, excerpt=segment.content)
        for segment in segments.values()
    ]

    grouped = group_evidence_by_chapter(
        evidence,
        segment_lookup=segments,
        max_segments_per_chapter=2,
    )

    assert [chapter for chapter, _ in grouped] == ["第一回", "第二回"]
    assert [len(items) for _, items in grouped] == [2, 2]


def test_merge_chapter_payloads_deduplicates_relationships_and_events() -> None:
    merged = merge_chapter_payloads(
        [
            {
                "chapter_key": "第一回",
                "source_segments": ["seg_1", "seg_2"],
                "trait_evidence": [{"segment_id": "seg_1", "excerpt": "谨慎"}],
                "motivation_evidence": [{"segment_id": "seg_2", "excerpt": "想保住门规"}],
                "relationship_mentions": [
                    {"target_name": "令狐冲", "chapter_key": "第一回", "source_segments": ["seg_1"], "excerpt": "训斥令狐冲"}
                ],
                "events": [{"title": "训诫弟子", "timeline_pos": 1, "source_segments": ["seg_1"], "excerpt": "训诫"}],
                "memories": [{"content": "训斥弟子", "source_event_id": None, "source_segments": ["seg_1"]}],
                "temporal_snapshot_candidates": [{"period_label": "第一回", "timeline_pos": 1, "source_segments": ["seg_1"]}],
            },
            {
                "chapter_key": "第二回",
                "source_segments": ["seg_2", "seg_3"],
                "trait_evidence": [{"segment_id": "seg_1", "excerpt": "谨慎"}],
                "motivation_evidence": [{"segment_id": "seg_3", "excerpt": "决定设局"}],
                "relationship_mentions": [
                    {"target_name": "令狐冲", "chapter_key": "第二回", "source_segments": ["seg_3"], "excerpt": "开始怀疑令狐冲"}
                ],
                "events": [{"title": "训诫弟子", "timeline_pos": 1, "source_segments": ["seg_3"], "excerpt": "重复事件"}],
                "memories": [{"content": "训斥弟子", "source_event_id": None, "source_segments": ["seg_3"]}],
                "temporal_snapshot_candidates": [{"period_label": "第二回", "timeline_pos": 2, "source_segments": ["seg_3"]}],
            },
        ]
    )

    assert merged["source_segments"] == ["seg_1", "seg_2", "seg_3"]
    assert len(merged["trait_evidence"]) == 1
    assert len(merged["motivation_evidence"]) == 2
    assert len(merged["relationship_mentions"]) == 2
    assert len(merged["events"]) == 1
    assert len(merged["memories"]) == 1
