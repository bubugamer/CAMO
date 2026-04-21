from __future__ import annotations

from camo.extraction.pipeline import preprocess_text


def test_novel_pipeline_preserves_chapter_information() -> None:
    text = (
        "第一回 风起\n"
        "“林平之”走入大堂。" + "江湖风声正紧。" * 120 + "\n\n"
        "第二回 远行\n"
        "令狐冲抬头看天。" + "他似笑非笑。" * 120
    )

    result = preprocess_text(text)

    assert result.source_type == "novel"
    assert len(result.segments) >= 2
    assert result.segments[0].chapter == "第一回 风起"
    assert result.segments[0].metadata["has_dialogue"] is True


def test_chat_pipeline_groups_messages_into_rounds() -> None:
    text = (
        "2026-03-15 14:32:05 张三\n今天下午开会吧\n\n"
        "2026-03-15 14:32:45 李四\n好的，几点？\n\n"
        "2026-03-15 15:20:00 张三\n三点，老地方"
    )

    result = preprocess_text(text)

    assert result.source_type == "chat"
    assert len(result.segments) == 2
    assert result.segments[0].metadata["participants"] == ["张三", "李四"]


def test_plain_pipeline_builds_overlapping_segments_for_long_text() -> None:
    text = ("这是一段普通文本。" * 220).strip()

    result = preprocess_text(text, "plain")

    assert result.source_type == "plain"
    assert len(result.segments) >= 2
    assert result.segments[0].content[-200:] == result.segments[1].content[:200]


def test_explicit_source_type_is_preserved_when_parser_falls_back() -> None:
    text = ("这是一段没有章节标题的长篇正文。" * 220).strip()

    result = preprocess_text(text, "novel")

    assert result.source_type == "novel"
    assert result.metadata["requested_source_type"] == "novel"
    assert result.metadata["parser_source_type"] == "plain"
    assert len(result.segments) >= 2
