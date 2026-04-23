from __future__ import annotations

from camo.extraction.detector import detect_source_type


def test_detects_novel_text() -> None:
    text = "第一回 风起\n林平之出门。\n\n第二回 远行\n令狐冲出现。"
    assert detect_source_type(text) == "novel"


def test_detects_chat_text() -> None:
    text = "2026-03-15 14:32:05 张三\n今天下午开会吧"
    assert detect_source_type(text) == "chat"


def test_detects_interview_text() -> None:
    text = "Q: 你为什么离开华山？\nA: 因为局势已经变了。\nQ: 你后悔吗？"
    assert detect_source_type(text) == "interview"


def test_detects_script_text() -> None:
    text = "第一幕\n第一场\n岳不群: 规矩不可乱。\n令狐冲: 弟子明白。\n宁中则: 先坐下再说。"
    assert detect_source_type(text) == "script"


def test_falls_back_to_plain_text() -> None:
    assert detect_source_type("这是一段普通说明文字。") == "plain"
