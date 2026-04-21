from __future__ import annotations

from camo.extraction.parsers.utils import chunk_text
from camo.extraction.types import PreprocessResult


def parse_plain(text: str) -> PreprocessResult:
    segments = chunk_text(text, target_size=1400, min_size=800, max_size=1800, overlap=200)
    return PreprocessResult(
        source_type="plain",
        normalized_content=text,
        segments=segments,
        metadata={"segment_count": len(segments)},
    )
