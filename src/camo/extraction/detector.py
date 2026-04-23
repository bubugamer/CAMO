from __future__ import annotations

import re

CHAT_HEADER_PATTERN = re.compile(r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [^\n]+$")
NOVEL_CHAPTER_PATTERN = re.compile(r"(?m)^第[一二三四五六七八九十百零\d]+[章回节卷][^\n]*$")
INTERVIEW_LINE_PATTERN = re.compile(r"(?m)^(?:Q|A|问|答)[:：]\s*.+$")
SCRIPT_DIALOGUE_PATTERN = re.compile(
    r"(?m)^(?!Q[:：])(?!A[:：])(?!问[:：])(?!答[:：])[^:：\n]{1,30}[:：]\s*.+$"
)


def detect_source_type(text: str) -> str:
    if CHAT_HEADER_PATTERN.search(text):
        return "chat"
    if NOVEL_CHAPTER_PATTERN.search(text):
        return "novel"
    if len(INTERVIEW_LINE_PATTERN.findall(text)) >= 2:
        return "interview"
    if len(SCRIPT_DIALOGUE_PATTERN.findall(text)) >= 3:
        return "script"
    return "plain"
