from __future__ import annotations

from dataclasses import replace
import re

from camo.extraction.parsers.plain import parse_plain
from camo.extraction.types import PreprocessResult, SegmentDraft

ACT_PATTERN = re.compile(r"^(?:第[一二三四五六七八九十百零\d]+幕.*|act\s+\w+.*)$", re.IGNORECASE)
SCENE_PATTERN = re.compile(r"^(?:第[一二三四五六七八九十百零\d]+场.*|scene\s+\w+.*)$", re.IGNORECASE)
DIALOGUE_PATTERN = re.compile(r"^(?P<speaker>[^:：\n]{1,30})[:：]\s*(?P<content>.+)$")


def parse_script(text: str) -> PreprocessResult:
    lines = text.splitlines()
    entries: list[dict[str, object]] = []
    current_act: str | None = None
    current_scene: str | None = None
    offset = 0
    line_index = 0

    for raw_line in lines:
        stripped = raw_line.strip()
        if ACT_PATTERN.match(stripped):
            current_act = stripped
            offset += len(raw_line) + 1
            continue
        if SCENE_PATTERN.match(stripped):
            current_scene = stripped
            offset += len(raw_line) + 1
            continue

        dialogue = DIALOGUE_PATTERN.match(stripped)
        if dialogue is None:
            offset += len(raw_line) + 1
            continue

        speaker = dialogue.group("speaker").strip()
        content = dialogue.group("content").strip()
        if not speaker or not content:
            offset += len(raw_line) + 1
            continue

        line_index += 1
        entries.append(
            {
                "speaker": speaker,
                "content": content,
                "act": current_act,
                "scene": current_scene,
                "offset": offset,
                "line_index": line_index,
            }
        )
        offset += len(raw_line) + 1

    if not entries:
        return parse_plain(text)

    segments = _group_entries(entries)
    return PreprocessResult(
        source_type="script",
        normalized_content=text,
        segments=segments,
        metadata={
            "line_count": len(entries),
            "segment_count": len(segments),
        },
    )


def _group_entries(entries: list[dict[str, object]], *, target_chars: int = 1400) -> list[SegmentDraft]:
    segments: list[SegmentDraft] = []
    group: list[dict[str, object]] = []
    group_chars = 0
    segment_index = 0

    for entry in entries:
        rendered = f"{entry['speaker']}: {entry['content']}"
        if group and group_chars + len(rendered) > target_chars:
            segment_index += 1
            segments.append(_build_segment(group, segment_index))
            group = []
            group_chars = 0
        group.append(entry)
        group_chars += len(rendered) + 1

    if group:
        segment_index += 1
        segments.append(_build_segment(group, segment_index))

    return segments


def _build_segment(group: list[dict[str, object]], segment_index: int) -> SegmentDraft:
    rendered_lines = [f"{entry['speaker']}: {entry['content']}" for entry in group]
    acts = [str(entry["act"]) for entry in group if entry.get("act")]
    scenes = [str(entry["scene"]) for entry in group if entry.get("scene")]
    line_numbers = [int(entry["line_index"]) for entry in group]
    participants = sorted({str(entry["speaker"]) for entry in group})

    chapter = " / ".join(part for part in [acts[-1] if acts else None, scenes[-1] if scenes else None] if part) or None
    draft = SegmentDraft(
        content="\n".join(rendered_lines),
        raw_offset=int(group[0]["offset"]),
        char_count=len("\n".join(rendered_lines)),
        chapter=chapter,
        metadata={
            "participants": participants,
            "source_progress": {
                "source_type": "script",
                "act": acts[-1] if acts else None,
                "scene": scenes[-1] if scenes else None,
                "line_start": min(line_numbers),
                "line_end": max(line_numbers),
                "segment_index": segment_index,
            },
        },
    )
    return replace(draft, metadata={key: value for key, value in draft.metadata.items() if value is not None})
