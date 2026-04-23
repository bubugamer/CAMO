from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.schemas import TextImportRequest, TextImportResponse, TextSegmentResponse, TextSourceResponse
from camo.db.queries.projects import get_project
from camo.db.queries.texts import get_text_source, list_text_segments, list_text_sources
from camo.texts import decode_text_bytes
from camo.texts.service import import_text_source

router = APIRouter(prefix="/projects/{project_id}/texts", tags=["texts"])


@router.post("", response_model=TextImportResponse, status_code=status.HTTP_201_CREATED, dependencies=[write_rate_limit])
async def import_text_endpoint(
    project_id: str,
    payload: TextImportRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TextImportResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    source, result = await import_text_source(
        session=session,
        project_id=project_id,
        payload=payload,
        data_root=request.app.state.settings.data_root,
    )
    return TextImportResponse(
        source_id=source.source_id,
        project_id=source.project_id,
        source_type=source.source_type,
        filename=source.filename,
        file_path=source.file_path or "",
        char_count=source.char_count or 0,
        segment_count=len(result.segments),
        metadata=source.source_metadata,
    )


@router.post(
    "/upload",
    response_model=TextImportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[write_rate_limit],
)
async def upload_text_file_endpoint(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
    source_type: str | None = Form(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> TextImportResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    raw = await file.read()
    content, encoding = decode_text_bytes(raw)
    payload = TextImportRequest(
        filename=file.filename,
        content=content,
        source_type=source_type,  # type: ignore[arg-type]
        encoding=encoding,
    )
    source, result = await import_text_source(
        session=session,
        project_id=project_id,
        payload=payload,
        data_root=request.app.state.settings.data_root,
    )
    return TextImportResponse(
        source_id=source.source_id,
        project_id=source.project_id,
        source_type=source.source_type,
        filename=source.filename,
        file_path=source.file_path or "",
        char_count=source.char_count or 0,
        segment_count=len(result.segments),
        metadata=source.source_metadata,
    )


@router.get("", response_model=list[TextSourceResponse], dependencies=[read_rate_limit])
async def list_text_sources_endpoint(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[TextSourceResponse]:
    sources = await list_text_sources(session, project_id)
    return [
        TextSourceResponse(
            source_id=source.source_id,
            project_id=source.project_id,
            filename=source.filename,
            source_type=source.source_type,
            file_path=source.file_path,
            char_count=source.char_count,
            metadata=source.source_metadata,
            created_at=source.created_at,
        )
        for source in sources
    ]


@router.get("/{source_id}", response_model=TextSourceResponse, dependencies=[read_rate_limit])
async def get_text_source_endpoint(
    project_id: str,
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> TextSourceResponse:
    source = await get_text_source(session, project_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text source not found")
    return TextSourceResponse(
        source_id=source.source_id,
        project_id=source.project_id,
        filename=source.filename,
        source_type=source.source_type,
        file_path=source.file_path,
        char_count=source.char_count,
        metadata=source.source_metadata,
        created_at=source.created_at,
    )


@router.get("/{source_id}/segments", response_model=list[TextSegmentResponse], dependencies=[read_rate_limit])
async def list_text_segments_endpoint(
    project_id: str,
    source_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[TextSegmentResponse]:
    source = await get_text_source(session, project_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text source not found")

    segments = await list_text_segments(session, source_id)
    return [
        TextSegmentResponse(
            segment_id=segment.segment_id,
            source_id=segment.source_id,
            position=segment.position,
            chapter=segment.chapter,
            round=segment.round,
            content=segment.content,
            raw_offset=segment.raw_offset,
            char_count=segment.char_count,
            metadata=segment.segment_metadata,
            created_at=segment.created_at,
        )
        for segment in segments
    ]
