from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from camo.core.schemas import TextImportRequest
from camo.db.models import TextSegment, TextSource
from camo.db.queries.texts import add_text_segments, create_text_source, get_project_max_timeline_pos
from camo.extraction.pipeline import preprocess_text
from camo.texts.storage import save_source_text


async def import_text_source(
    *,
    session: AsyncSession,
    project_id: str,
    payload: TextImportRequest,
    data_root: Path,
) -> tuple[TextSource, object]:
    source_id = f"src_{uuid4().hex[:12]}"
    processed = preprocess_text(payload.content, payload.source_type)
    timeline_offset = await get_project_max_timeline_pos(session, project_id)
    stored_path = save_source_text(
        data_root=data_root,
        source_id=source_id,
        content=payload.content,
    )

    estimated_page_count = max(1, (len(processed.normalized_content) + 799) // 800)
    source_metadata = {
        **processed.metadata,
        "normalized": True,
        "estimated_page_count": estimated_page_count,
    }
    if payload.encoding:
        source_metadata["encoding"] = payload.encoding
    source = TextSource(
        source_id=source_id,
        project_id=project_id,
        filename=payload.filename,
        source_type=processed.source_type,
        file_path=stored_path,
        char_count=len(processed.normalized_content),
        source_metadata=source_metadata,
    )
    await create_text_source(session, source)

    segment_rows = [
        TextSegment(
            segment_id=f"seg_{source_id}_{position:04d}",
            source_id=source_id,
            position=position,
            chapter=segment.chapter,
            round=segment.round,
            content=segment.content,
            raw_offset=segment.raw_offset,
            char_count=segment.char_count,
            segment_metadata=_augment_segment_metadata(
                segment.metadata,
                timeline_pos=timeline_offset + position,
                raw_offset=segment.raw_offset,
                char_count=segment.char_count,
            ),
        )
        for position, segment in enumerate(processed.segments, start=1)
    ]
    await add_text_segments(session, segment_rows)
    await session.commit()
    await session.refresh(source)
    return source, processed


def _augment_segment_metadata(
    metadata: dict,
    *,
    timeline_pos: int,
    raw_offset: int,
    char_count: int,
) -> dict:
    enriched = dict(metadata)
    enriched["timeline_pos"] = timeline_pos

    source_progress = dict(enriched.get("source_progress", {}) or {})
    page_start = raw_offset // 800 + 1
    page_end = max(page_start, (raw_offset + max(char_count - 1, 0)) // 800 + 1)
    source_progress.setdefault("page_start", page_start)
    source_progress.setdefault("page_end", page_end)
    enriched["source_progress"] = source_progress
    return enriched
