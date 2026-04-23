from __future__ import annotations

from dataclasses import replace

from camo.extraction.detector import detect_source_type
from camo.extraction.parsers.chat import parse_chat
from camo.extraction.parsers.interview import parse_interview
from camo.extraction.parsers.novel import parse_novel
from camo.extraction.parsers.plain import parse_plain
from camo.extraction.parsers.script import parse_script
from camo.extraction.parsers.utils import normalize_text
from camo.extraction.types import PreprocessResult


PARSERS = {
    "chat": parse_chat,
    "interview": parse_interview,
    "novel": parse_novel,
    "plain": parse_plain,
    "script": parse_script,
}


def preprocess_text(content: str, source_type: str | None = None) -> PreprocessResult:
    normalized = normalize_text(content)
    detected_type = detect_source_type(normalized)
    resolved_type = source_type or detected_type
    parser = PARSERS[resolved_type]
    parsed = _attach_timeline_metadata(parser(normalized))
    metadata = {
        **parsed.metadata,
        "detected_type": detected_type,
    }

    if source_type is not None:
        metadata["requested_source_type"] = source_type
        if parsed.source_type != source_type:
            metadata["parser_source_type"] = parsed.source_type
        return PreprocessResult(
            source_type=source_type,
            normalized_content=parsed.normalized_content,
            segments=parsed.segments,
            metadata=metadata,
        )

    return PreprocessResult(
        source_type=parsed.source_type,
        normalized_content=parsed.normalized_content,
        segments=parsed.segments,
        metadata=metadata,
    )


def _attach_timeline_metadata(result: PreprocessResult) -> PreprocessResult:
    enriched_segments = []
    for timeline_pos, segment in enumerate(result.segments, start=1):
        metadata = dict(segment.metadata)
        metadata["timeline_pos"] = timeline_pos
        metadata.setdefault(
            "source_progress",
            {
                "source_type": result.source_type,
                "segment_index": timeline_pos,
            },
        )
        enriched_segments.append(replace(segment, metadata=metadata))

    return PreprocessResult(
        source_type=result.source_type,
        normalized_content=result.normalized_content,
        segments=enriched_segments,
        metadata=result.metadata,
    )
