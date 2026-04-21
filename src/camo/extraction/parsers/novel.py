from __future__ import annotations

import re

from camo.extraction.parsers.plain import parse_plain
from camo.extraction.parsers.utils import chunk_text
from camo.extraction.types import PreprocessResult, SegmentDraft

CHAPTER_PATTERN = re.compile(r"(?m)^第[一二三四五六七八九十百零\d]+[章回节卷][^\n]*$")


def parse_novel(text: str) -> PreprocessResult:
    matches = list(CHAPTER_PATTERN.finditer(text))
    if not matches:
        return parse_plain(text)

    segments: list[SegmentDraft] = []
    for index, match in enumerate(matches):
        chapter_start = match.start()
        chapter_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chapter_text = text[chapter_start:chapter_end].strip("\n")
        leading_trim = len(text[chapter_start:chapter_end]) - len(text[chapter_start:chapter_end].lstrip("\n"))
        chapter_title = match.group(0).strip()
        segments.extend(
            chunk_text(
                chapter_text,
                chapter=chapter_title,
                start_offset=chapter_start + leading_trim,
                target_size=1400,
                min_size=900,
                max_size=1800,
                overlap=200,
            )
        )

    return PreprocessResult(
        source_type="novel",
        normalized_content=text,
        segments=segments,
        metadata={
            "chapter_count": len(matches),
            "segment_count": len(segments),
        },
    )
