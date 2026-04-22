from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session, get_model_adapter
from camo.core.schemas import (
    CharacterDetailResponse,
    CharacterChatRequest,
    CharacterChatResponse,
    CharacterIndexResponse,
    CharacterIndexRunRequest,
    CharacterIndexRunResponse,
    CharacterPortraitRequest,
    CharacterPortraitResponse,
    EventRecordResponse,
    MemoryRecordResponse,
)
from camo.db.queries.characters import get_character, list_characters
from camo.db.queries.events import list_events_for_character
from camo.db.queries.memories import list_memories_for_character
from camo.db.queries.projects import get_project
from camo.db.queries.texts import get_text_source
from camo.extraction.pass1 import run_character_index
from camo.extraction.pass2 import run_character_portrait
from camo.models.adapter import ModelAdapter, ProviderConfigurationError
from camo.runtime import run_character_chat

router = APIRouter(tags=["characters"])


@router.post(
    "/projects/{project_id}/texts/{source_id}/character-index",
    response_model=CharacterIndexRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_character_index_endpoint(
    project_id: str,
    source_id: str,
    payload: CharacterIndexRunRequest,
    session: AsyncSession = Depends(get_db_session),
    adapter: ModelAdapter = Depends(get_model_adapter),
) -> CharacterIndexRunResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    source = await get_text_source(session, project_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text source not found")

    try:
        characters, processed_segments = await run_character_index(
            session=session,
            model_adapter=adapter,
            project_id=project_id,
            source_id=source_id,
            source_type=source.source_type,
            segment_limit=payload.segment_limit,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CharacterIndexRunResponse(
        project_id=project_id,
        source_id=source_id,
        processed_segments=processed_segments,
        character_count=len(characters),
        characters=[_to_character_index_response(character) for character in characters],
    )


@router.post(
    "/projects/{project_id}/texts/{source_id}/character-portrait",
    response_model=CharacterPortraitResponse,
    status_code=status.HTTP_201_CREATED,
)
async def run_character_portrait_endpoint(
    project_id: str,
    source_id: str,
    payload: CharacterPortraitRequest,
    session: AsyncSession = Depends(get_db_session),
    adapter: ModelAdapter = Depends(get_model_adapter),
) -> CharacterPortraitResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    source = await get_text_source(session, project_id, source_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Text source not found")

    try:
        character, events, memories, processed_segments, matched_segment_ids = await run_character_portrait(
            session=session,
            model_adapter=adapter,
            project_id=project_id,
            source_id=source_id,
            source_type=source.source_type,
            name=payload.name,
            aliases=payload.aliases,
            max_segments=payload.max_segments,
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    character_index = character.character_index
    return CharacterPortraitResponse(
        project_id=project_id,
        source_id=source_id,
        character_id=character.character_id,
        name=character_index.get("name", payload.name),
        aliases=character_index.get("aliases", []),
        processed_segments=processed_segments,
        matched_segment_ids=matched_segment_ids,
        character_core=character.character_core or {},
        character_facet=character.character_facet or {},
        events=[_to_event_response(event) for event in events],
        memories=[_to_memory_response(memory) for memory in memories],
    )


@router.get("/projects/{project_id}/characters", response_model=list[CharacterIndexResponse])
async def list_characters_endpoint(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[CharacterIndexResponse]:
    characters = await list_characters(session, project_id)
    return [_to_character_index_response(character) for character in characters]


@router.get("/projects/{project_id}/characters/{character_id}", response_model=CharacterDetailResponse)
async def get_character_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterDetailResponse:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return _to_character_detail_response(character)


@router.get(
    "/projects/{project_id}/characters/{character_id}/events",
    response_model=list[EventRecordResponse],
)
async def list_character_events_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[EventRecordResponse]:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    events = await list_events_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    return [_to_event_response(event) for event in events]


@router.get(
    "/projects/{project_id}/characters/{character_id}/memories",
    response_model=list[MemoryRecordResponse],
)
async def list_character_memories_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryRecordResponse]:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    memories = await list_memories_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    return [_to_memory_response(memory) for memory in memories]


@router.post(
    "/projects/{project_id}/characters/{character_id}/chat",
    response_model=CharacterChatResponse,
)
async def chat_with_character_endpoint(
    project_id: str,
    character_id: str,
    payload: CharacterChatRequest,
    session: AsyncSession = Depends(get_db_session),
    adapter: ModelAdapter = Depends(get_model_adapter),
) -> CharacterChatResponse:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    memories = await list_memories_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    try:
        result = await run_character_chat(
            model_adapter=adapter,
            character=character,
            memories=memories,
            user_message=payload.message,
            history=[item.model_dump() for item in payload.history[-8:]],
        )
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CharacterChatResponse(
        character_id=character_id,
        reply=result["reply"],
        tone=result["tone"],
        style_tags=result.get("style_tags", []),
        speaker=result.get("speaker"),
        reasoning_summary=result.get("reasoning_summary"),
        consistency_check=result.get("consistency_check"),
        memory_count=result["memory_count"],
    )


def _to_character_index_response(character) -> CharacterIndexResponse:
    character_index = character.character_index
    first_appearance = character_index.get("first_appearance")
    if isinstance(first_appearance, dict):
        first_appearance = first_appearance.get("segment_id")
    return CharacterIndexResponse(
        character_id=character.character_id,
        project_id=character.project_id,
        schema_version=character_index.get("schema_version", character.schema_version),
        name=character_index.get("name", ""),
        description=character_index.get("description", ""),
        character_type=_coerce_character_type(character_index.get("character_type")),
        aliases=character_index.get("aliases", []),
        titles=character_index.get("titles", []),
        identities=character_index.get("identities", []),
        first_appearance=first_appearance,
        confidence=character_index.get("confidence", 0.0),
        source_segments=character_index.get("source_segments", []),
        status=character.status,
        created_at=character.created_at,
        updated_at=character.updated_at,
    )


def _to_character_detail_response(character) -> CharacterDetailResponse:
    payload = _to_character_index_response(character).model_dump()
    return CharacterDetailResponse(
        **payload,
        character_core=character.character_core,
        character_facet=character.character_facet,
    )


def _to_event_response(event) -> EventRecordResponse:
    return EventRecordResponse(
        event_id=event.event_id,
        schema_version=event.schema_version,
        title=event.title,
        description=event.description,
        timeline_pos=event.timeline_pos,
        participant_character_ids=event.participants,
        location=event.location,
        emotion_valence=event.emotion_valence,
        source_segments=event.source_segments,
        created_at=event.created_at,
    )


def _to_memory_response(memory) -> MemoryRecordResponse:
    return MemoryRecordResponse(
        memory_id=memory.memory_id,
        character_id=memory.character_id,
        project_id=memory.project_id,
        schema_version=memory.schema_version,
        memory_type=memory.memory_type,
        salience=memory.salience,
        recency=memory.recency,
        content=memory.content,
        source_event_id=memory.source_event_id,
        related_character_ids=memory.related_character_ids,
        emotion_valence=memory.emotion_valence,
        source_segments=memory.source_segments,
        created_at=memory.created_at,
    )


def _coerce_character_type(value: str | None) -> str:
    text = (value or "").strip()
    if text in {
        "fictional_person",
        "real_person",
        "group_persona",
        "virtual_persona",
        "unnamed_person",
        "unidentified_person",
    }:
        return text
    return "unidentified_person"
