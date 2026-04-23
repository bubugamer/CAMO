from __future__ import annotations

from dataclasses import replace
import re

from camo.extraction.parsers.plain import parse_plain
from camo.extraction.types import PreprocessResult, SegmentDraft

INTERVIEW_LINE_PATTERN = re.compile(r"^(?P<label>Q|A|问|答)[:：]\s*(?P<content>.+)$", re.IGNORECASE)


def parse_interview(text: str) -> PreprocessResult:
    lines = text.splitlines()
    entries: list[dict[str, object]] = []
    offset = 0
    question_index = 0

    for raw_line in lines:
        stripped = raw_line.strip()
        match = INTERVIEW_LINE_PATTERN.match(stripped)
        if match is None:
            offset += len(raw_line) + 1
            continue

        label = match.group("label")
        content = match.group("content").strip()
        if not content:
            offset += len(raw_line) + 1
            continue

        speaker = "Interviewer" if label.lower() == "q" or label == "问" else "Interviewee"
        if speaker == "Interviewer":
            question_index += 1

        entries.append(
            {
                "speaker": speaker,
                "content": content,
                "offset": offset,
                "question_index": question_index or 1,
            }
        )
        offset += len(raw_line) + 1

    if not entries:
        return parse_plain(text)

    segments = _group_entries(entries)
    return PreprocessResult(
        source_type="interview",
        normalized_content=text,
        segments=segments,
        metadata={
            "turn_count": len(entries),
            "question_count": max(int(entry["question_index"]) for entry in entries),
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
    question_numbers = [int(entry["question_index"]) for entry in group]
    participants = sorted({str(entry["speaker"]) for entry in group})

    draft = SegmentDraft(
        content="\n".join(rendered_lines),
        raw_offset=int(group[0]["offset"]),
        char_count=len("\n".join(rendered_lines)),
        round=segment_index,
        metadata={
            "participants": participants,
            "source_progress": {
                "source_type": "interview",
                "question_index_start": min(question_numbers),
                "question_index_end": max(question_numbers),
                "segment_index": segment_index,
            },
        },
    )
    return replace(draft, metadata={key: value for key, value in draft.metadata.items() if value is not None})
