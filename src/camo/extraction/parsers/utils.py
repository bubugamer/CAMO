from __future__ import annotations

import re

from camo.extraction.types import SegmentDraft


def normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    return normalized


def has_dialogue(text: str) -> bool:
    return any(token in text for token in ['"', "“", "”", "「", "」", "："])


def sentence_and_paragraph_breakpoints(text: str) -> list[int]:
    breakpoints = {len(text)}
    for pattern in (r"\n{2,}", r"[。！？!?]\s*", r"\n"):
        for match in re.finditer(pattern, text):
            breakpoints.add(match.end())
    return sorted(point for point in breakpoints if point > 0)


def chunk_text(
    text: str,
    *,
    chapter: str | None = None,
    round_num: int | None = None,
    start_offset: int = 0,
    target_size: int = 1400,
    min_size: int = 800,
    max_size: int = 1800,
    overlap: int = 200,
) -> list[SegmentDraft]:
    if not text:
        return []

    breakpoints = sentence_and_paragraph_breakpoints(text)
    base_spans: list[tuple[int, int]] = []
    cursor = 0

    while cursor < len(text):
        remaining = len(text) - cursor
        if remaining <= max_size:
            end = len(text)
        else:
            min_end = min(len(text), cursor + min_size)
            target_end = min(len(text), cursor + target_size)
            max_end = min(len(text), cursor + max_size)
            candidates = [point for point in breakpoints if min_end <= point <= max_end]
            end = min(candidates, key=lambda point: (abs(point - target_end), point)) if candidates else max_end

        if end <= cursor:
            end = min(len(text), cursor + max_size)
        base_spans.append((cursor, end))
        cursor = end

    segments: list[SegmentDraft] = []
    for index, (base_start, base_end) in enumerate(base_spans):
        segment_start = base_start if index == 0 else max(0, base_start - overlap)
        segment_text = text[segment_start:base_end]
        segments.append(
            SegmentDraft(
                content=segment_text,
                raw_offset=start_offset + segment_start,
                char_count=len(segment_text),
                chapter=chapter,
                round=round_num,
                metadata={"has_dialogue": has_dialogue(segment_text)},
            )
        )
    return segments
