from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session, get_model_adapter
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.patching import build_structured_diff, deep_merge
from camo.core.schemas import (
    AnchorSnapshotResponse,
    CharacterDetailResponse,
    CharacterChatRequest,
    CharacterChatResponse,
    CharacterIndexResponse,
    CharacterIndexRunRequest,
    CharacterIndexRunResponse,
    CharacterPatchRequest,
    CharacterPortraitRequest,
    CharacterPortraitResponse,
    CharacterRollbackRequest,
    CharacterVersionResponse,
    EventRecordResponse,
    MemoryRecordResponse,
    RelationshipRecordResponse,
)
from camo.db.queries.characters import get_character, get_character_by_id, list_characters, save_character_assets
from camo.db.queries.events import list_events_for_character
from camo.db.queries.memories import list_memories_for_character
from camo.db.queries.projects import get_project
from camo.db.queries.reviews import create_review
from camo.db.queries.texts import get_text_source
from camo.db.queries.versions import create_character_version, list_versions_for_character
from camo.extraction.pass1 import run_character_index
from camo.extraction.pass2 import run_character_portrait
from camo.models.adapter import ModelAdapter, ProviderConfigurationError
from camo.runtime.anchors import list_character_anchors
from camo.runtime import run_character_chat
from camo.tasks.modeling import build_character_snapshot

router = APIRouter(tags=["characters"])


@router.post(
    "/projects/{project_id}/texts/{source_id}/character-index",
    response_model=CharacterIndexRunResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[write_rate_limit],
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
    dependencies=[write_rate_limit],
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
        (
            character,
            relationships,
            events,
            memories,
            processed_segments,
            matched_segment_ids,
        ) = await run_character_portrait(
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
        relationships=[_to_relationship_response(relationship) for relationship in relationships],
        events=[_to_event_response(event) for event in events],
        memories=[_to_memory_response(memory) for memory in memories],
    )


@router.get("/projects/{project_id}/characters", response_model=list[CharacterIndexResponse], dependencies=[read_rate_limit])
async def list_characters_endpoint(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[CharacterIndexResponse]:
    characters = await list_characters(session, project_id)
    return [_to_character_index_response(character) for character in characters]


@router.get(
    "/projects/{project_id}/characters/{character_id}",
    response_model=CharacterDetailResponse,
    dependencies=[read_rate_limit],
)
async def get_character_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterDetailResponse:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return _to_character_detail_response(character)


@router.get("/characters/{character_id}/index", response_model=CharacterIndexResponse, dependencies=[read_rate_limit])
async def get_character_index_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterIndexResponse:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return _to_character_index_response(character)


@router.get("/characters/{character_id}/core", dependencies=[read_rate_limit])
async def get_character_core_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return character.character_core or {}


@router.get("/characters/{character_id}/facet", dependencies=[read_rate_limit])
async def get_character_facet_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return character.character_facet or {}


@router.get(
    "/projects/{project_id}/characters/{character_id}/anchors",
    response_model=list[AnchorSnapshotResponse],
    dependencies=[read_rate_limit],
)
async def list_character_anchors_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[AnchorSnapshotResponse]:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    return [AnchorSnapshotResponse(**item) for item in list_character_anchors(character)]


@router.get(
    "/projects/{project_id}/characters/{character_id}/events",
    response_model=list[EventRecordResponse],
    dependencies=[read_rate_limit],
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
    dependencies=[read_rate_limit],
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


@router.get("/characters/{character_id}/memories", response_model=list[MemoryRecordResponse], dependencies=[read_rate_limit])
async def list_character_memories_by_id_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[MemoryRecordResponse]:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    memories = await list_memories_for_character(
        session,
        project_id=character.project_id,
        character_id=character_id,
    )
    return [_to_memory_response(memory) for memory in memories]


@router.post(
    "/projects/{project_id}/characters/{character_id}/chat",
    response_model=CharacterChatResponse,
    dependencies=[write_rate_limit],
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


@router.patch("/characters/{character_id}", response_model=CharacterDetailResponse, dependencies=[write_rate_limit])
async def patch_character_endpoint(
    character_id: str,
    payload: CharacterPatchRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterDetailResponse:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    before = build_character_snapshot(character)
    next_index = deep_merge(character.character_index, payload.character_index_patch) if payload.character_index_patch else character.character_index
    next_core = (
        deep_merge(character.character_core or {}, payload.character_core_patch)
        if payload.character_core_patch
        else character.character_core
    )
    next_facet = (
        deep_merge(character.character_facet or {}, payload.character_facet_patch)
        if payload.character_facet_patch
        else character.character_facet
    )
    await save_character_assets(
        session,
        character,
        character_index=next_index,
        character_core=next_core,
        character_facet=next_facet,
        status=payload.status or character.status,
    )
    after = build_character_snapshot(character)
    diff = build_structured_diff(before, after)
    await create_character_version(
        session,
        character_id=character.character_id,
        snapshot=after,
        diff=diff,
        created_by=payload.reviewer,
        note=payload.note or "Character patch update",
    )
    await create_review(
        session,
        target_type="character_asset",
        target_id=character.character_id,
        diff=diff,
        reviewer=payload.reviewer,
        status="approved" if payload.reviewer else "pending",
        note=payload.note,
    )
    return _to_character_detail_response(character)


@router.get("/characters/{character_id}/versions", response_model=list[CharacterVersionResponse], dependencies=[read_rate_limit])
async def list_character_versions_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[CharacterVersionResponse]:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    versions = await list_versions_for_character(session, character_id=character_id)
    return [
        CharacterVersionResponse(
            version_id=item.version_id,
            character_id=item.character_id,
            version_num=item.version_num,
            snapshot=item.snapshot,
            diff=item.diff,
            created_by=item.created_by,
            note=item.note,
            created_at=item.created_at,
        )
        for item in versions
    ]


@router.post("/characters/{character_id}/rollback", response_model=CharacterDetailResponse, dependencies=[write_rate_limit])
async def rollback_character_endpoint(
    character_id: str,
    payload: CharacterRollbackRequest,
    session: AsyncSession = Depends(get_db_session),
) -> CharacterDetailResponse:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    versions = await list_versions_for_character(session, character_id=character_id)
    target = next((item for item in versions if item.version_id == payload.version_id), None)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    before = build_character_snapshot(character)
    snapshot = target.snapshot
    await save_character_assets(
        session,
        character,
        character_index=snapshot.get("character_index"),
        character_core=snapshot.get("character_core"),
        character_facet=snapshot.get("character_facet"),
        status=snapshot.get("status", character.status),
    )
    after = build_character_snapshot(character)
    diff = build_structured_diff(before, after)
    await create_character_version(
        session,
        character_id=character.character_id,
        snapshot=after,
        diff=diff,
        created_by=payload.reviewer,
        note=payload.note or f"Rollback to {payload.version_id}",
    )
    await create_review(
        session,
        target_type="character_asset",
        target_id=character.character_id,
        diff=diff,
        reviewer=payload.reviewer,
        status="approved" if payload.reviewer else "pending",
        note=payload.note or f"Rollback to {payload.version_id}",
    )
    return _to_character_detail_response(character)


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


def _to_relationship_response(relationship) -> RelationshipRecordResponse:
    return RelationshipRecordResponse(
        relationship_id=relationship.relationship_id,
        project_id=relationship.project_id,
        schema_version=relationship.schema_version,
        source_character_id=relationship.source_id,
        target_character_id=relationship.target_id,
        relation_category=relationship.relation_category,
        relation_subtype=relationship.relation_subtype,
        public_state=relationship.public_state,
        hidden_state=relationship.hidden_state,
        timeline=relationship.timeline,
        source_segments=relationship.source_segments,
        confidence=relationship.confidence,
        created_at=relationship.created_at,
        updated_at=relationship.updated_at,
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
