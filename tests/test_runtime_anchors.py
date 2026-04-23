from __future__ import annotations

import asyncio
from types import SimpleNamespace

from camo.db.models import Character, TextSegment, TextSource
from camo.runtime import anchors as anchors_module
from camo.runtime.anchors import find_best_snapshot, resolve_anchor


def test_find_best_snapshot_prefers_containing_then_latest_prior() -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_facet={
            "temporal_snapshots": [
                {
                    "snapshot_id": "snap_1",
                    "period_label": "早期",
                    "activation_range": {"start_timeline_pos": 1, "end_timeline_pos": 4},
                },
                {
                    "snapshot_id": "snap_2",
                    "period_label": "中期",
                    "activation_range": {"start_timeline_pos": 5, "end_timeline_pos": 9},
                },
            ]
        },
    )

    assert find_best_snapshot(character, 6)["snapshot_id"] == "snap_2"
    assert find_best_snapshot(character, 12)["snapshot_id"] == "snap_2"


def test_resolve_anchor_maps_source_progress(monkeypatch) -> None:
    character = Character(
        character_id="char_demo",
        project_id="proj_demo",
        character_index={"name": "岳不群"},
        character_facet={
            "temporal_snapshots": [
                {
                    "snapshot_id": "snap_mid",
                    "period_label": "中期",
                    "activation_range": {"start_timeline_pos": 3, "end_timeline_pos": 6},
                    "display_hint": {"primary": "中期", "secondary": ""},
                    "stage_summary": "仍保留掌门体面。",
                }
            ]
        },
    )
    records = [
        SimpleNamespace(
            segment=TextSegment(
                segment_id="seg_1",
                source_id="src_1",
                position=1,
                chapter="第一回",
                round=None,
                content="早期。",
                raw_offset=0,
                char_count=3,
                segment_metadata={"timeline_pos": 2, "source_progress": {"chapter_index": 1, "page_end": 10}},
            ),
            source=TextSource(
                source_id="src_1",
                project_id="proj_demo",
                filename="demo.txt",
                source_type="novel",
                file_path="demo.txt",
                char_count=1000,
                source_metadata={},
            ),
        ),
        SimpleNamespace(
            segment=TextSegment(
                segment_id="seg_2",
                source_id="src_1",
                position=2,
                chapter="第二回",
                round=None,
                content="中期。",
                raw_offset=10,
                char_count=3,
                segment_metadata={"timeline_pos": 5, "source_progress": {"chapter_index": 2, "page_end": 20}},
            ),
            source=TextSource(
                source_id="src_1",
                project_id="proj_demo",
                filename="demo.txt",
                source_type="novel",
                file_path="demo.txt",
                char_count=1000,
                source_metadata={},
            ),
        ),
    ]
    async def fake_list_project_segment_records(session, project_id):
        return records

    monkeypatch.setattr(anchors_module, "list_project_segment_records", fake_list_project_segment_records)

    anchor_state, trace = asyncio.run(
        resolve_anchor(
            None,
            project_id="proj_demo",
            character=character,
            anchor_input={"anchor_mode": "source_progress", "source_type": "chapter", "cutoff_value": 2},
        )
    )

    assert anchor_state["resolved_timeline_pos"] == 5
    assert anchor_state["snapshot_id"] == "snap_mid"
    assert trace["source_type"] == "chapter"
