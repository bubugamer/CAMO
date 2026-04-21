from __future__ import annotations

import re

CHAT_HEADER_PATTERN = re.compile(r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [^\n]+$")
NOVEL_CHAPTER_PATTERN = re.compile(r"(?m)^第[一二三四五六七八九十百零\d]+[章回节卷][^\n]*$")


def detect_source_type(text: str) -> str:
    if CHAT_HEADER_PATTERN.search(text):
        return "chat"
    if NOVEL_CHAPTER_PATTERN.search(text):
        return "novel"
    return "plain"
