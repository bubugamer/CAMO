from __future__ import annotations

from datetime import datetime, timedelta
import re

from camo.extraction.types import PreprocessResult, SegmentDraft

MESSAGE_HEADER_PATTERN = re.compile(r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [^\n]+$")
TIME_GAP_THRESHOLD = timedelta(minutes=30)


def parse_chat(text: str) -> PreprocessResult:
    headers = list(MESSAGE_HEADER_PATTERN.finditer(text))
    if not headers:
        return PreprocessResult(source_type="chat", normalized_content=text, segments=[], metadata={"segment_count": 0})

    messages: list[dict] = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        header_line = header.group(0)
        timestamp_str, sender = header_line[:19], header_line[20:].strip()
        content = text[header.end():end].strip()
        messages.append(
            {
                "timestamp": datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S"),
                "sender": sender,
                "content": content,
                "offset": header.start(),
            }
        )

    grouped: list[list[dict]] = []
    current: list[dict] = []
    for message in messages:
        if not current:
            current = [message]
            continue
        gap = message["timestamp"] - current[-1]["timestamp"]
        if gap > TIME_GAP_THRESHOLD:
            grouped.append(current)
            current = [message]
        else:
            current.append(message)
    if current:
        grouped.append(current)

    rounds: list[list[dict]] = []
    for group in grouped:
        if len(group) > 50:
            for start in range(0, len(group), 30):
                rounds.append(group[start:start + 30])
        else:
            rounds.append(group)

    segments: list[SegmentDraft] = []
    for round_index, round_messages in enumerate(rounds, start=1):
        rendered_lines = [
            f"[{message['timestamp'].strftime('%H:%M:%S')} {message['sender']}] {message['content']}"
            for message in round_messages
        ]
        participants = sorted({message["sender"] for message in round_messages})
        segments.append(
            SegmentDraft(
                content="\n".join(rendered_lines),
                raw_offset=round_messages[0]["offset"],
                char_count=len("\n".join(rendered_lines)),
                round=round_index,
                metadata={
                    "participants": participants,
                    "timestamp_range": [
                        round_messages[0]["timestamp"].isoformat(),
                        round_messages[-1]["timestamp"].isoformat(),
                    ],
                },
            )
        )

    return PreprocessResult(
        source_type="chat",
        normalized_content=text,
        segments=segments,
        metadata={
            "message_count": len(messages),
            "segment_count": len(segments),
        },
    )
