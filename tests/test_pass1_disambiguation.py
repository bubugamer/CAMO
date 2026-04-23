from __future__ import annotations

from camo.extraction.pass1 import (
    CharacterMention,
    apply_disambiguation_decisions,
    build_disambiguation_candidates,
    initial_cluster_mentions,
)


def test_initial_clustering_keeps_same_name_mentions_separate_when_identity_is_ambiguous() -> None:
    mentions = [
        CharacterMention(
            name="张三",
            aliases=[],
            titles=["华山弟子"],
            identities=[],
            description="年轻弟子",
            character_type="fictional_person",
            segment_id="seg_1",
            position=1,
        ),
        CharacterMention(
            name="张三",
            aliases=[],
            titles=["镖局掌柜"],
            identities=[],
            description="年长掌柜",
            character_type="fictional_person",
            segment_id="seg_8",
            position=8,
        ),
    ]

    clusters = initial_cluster_mentions(mentions)
    candidates = build_disambiguation_candidates(clusters)

    assert len(clusters) == 2
    assert len(candidates) == 1


def test_disambiguation_decision_can_merge_clusters_after_conservative_split() -> None:
    mentions = [
        CharacterMention(
            name="岳掌门",
            aliases=[],
            titles=["华山掌门"],
            identities=[{"type": "role", "value": "华山掌门"}],
            description="掌门人",
            character_type="fictional_person",
            segment_id="seg_1",
            position=1,
        ),
        CharacterMention(
            name="君子剑",
            aliases=[],
            titles=["华山掌门"],
            identities=[{"type": "role", "value": "华山掌门"}],
            description="江湖人称君子剑",
            character_type="fictional_person",
            segment_id="seg_3",
            position=3,
        ),
    ]

    clusters = initial_cluster_mentions(mentions)
    merged = apply_disambiguation_decisions(
        clusters,
        [
            {
                "left_index": 0,
                "right_index": 1,
                "same_character": True,
                "confidence": 0.92,
                "reason": "称号与身份都一致",
            }
        ],
    )

    assert len(clusters) == 2
    assert len(merged) == 1
