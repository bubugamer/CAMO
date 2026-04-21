from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SegmentDraft:
    content: str
    raw_offset: int
    char_count: int
    chapter: str | None = None
    round: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PreprocessResult:
    source_type: str
    normalized_content: str
    segments: list[SegmentDraft]
    metadata: dict[str, Any]
