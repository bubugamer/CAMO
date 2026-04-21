from __future__ import annotations

from camo.extraction.detector import detect_source_type
from camo.extraction.parsers.chat import parse_chat
from camo.extraction.parsers.novel import parse_novel
from camo.extraction.parsers.plain import parse_plain
from camo.extraction.parsers.utils import normalize_text
from camo.extraction.types import PreprocessResult


PARSERS = {
    "chat": parse_chat,
    "novel": parse_novel,
    "plain": parse_plain,
}


def preprocess_text(content: str, source_type: str | None = None) -> PreprocessResult:
    normalized = normalize_text(content)
    detected_type = detect_source_type(normalized)
    resolved_type = source_type or detected_type
    parser = PARSERS[resolved_type]
    parsed = parser(normalized)
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
