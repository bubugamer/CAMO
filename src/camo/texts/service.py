from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from camo.core.schemas import TextImportRequest
from camo.db.models import TextSegment, TextSource
from camo.db.queries.texts import add_text_segments, create_text_source
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
    stored_path = save_source_text(
        data_root=data_root,
        source_id=source_id,
        content=processed.normalized_content,
    )

    source_metadata = {**processed.metadata, "normalized": True}
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
            segment_metadata=segment.metadata,
        )
        for position, segment in enumerate(processed.segments, start=1)
    ]
    await add_text_segments(session, segment_rows)
    await session.commit()
    await session.refresh(source)
    return source, processed
