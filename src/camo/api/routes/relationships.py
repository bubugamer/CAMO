from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import read_rate_limit
from camo.core.schemas import RelationshipRecordResponse
from camo.db.queries.characters import get_character, get_character_by_id
from camo.db.queries.relationships import (
    get_relationship,
    get_relationship_by_id,
    list_relationships_for_character,
)

router = APIRouter(tags=["relationships"])


@router.get(
    "/projects/{project_id}/characters/{character_id}/relationships",
    response_model=list[RelationshipRecordResponse],
    dependencies=[read_rate_limit],
)
async def list_character_relationships_endpoint(
    project_id: str,
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[RelationshipRecordResponse]:
    character = await get_character(session, project_id, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")

    relationships = await list_relationships_for_character(
        session,
        project_id=project_id,
        character_id=character_id,
    )
    return [_to_relationship_response(item) for item in relationships]


@router.get(
    "/characters/{character_id}/relationships",
    response_model=list[RelationshipRecordResponse],
    dependencies=[read_rate_limit],
)
async def list_character_relationships_by_id_endpoint(
    character_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[RelationshipRecordResponse]:
    character = await get_character_by_id(session, character_id)
    if character is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Character not found")
    relationships = await list_relationships_for_character(
        session,
        project_id=character.project_id,
        character_id=character_id,
    )
    return [_to_relationship_response(item) for item in relationships]


@router.get(
    "/projects/{project_id}/relationships/{relationship_id}",
    response_model=RelationshipRecordResponse,
    dependencies=[read_rate_limit],
)
async def get_relationship_endpoint(
    project_id: str,
    relationship_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RelationshipRecordResponse:
    relationship = await get_relationship(
        session,
        project_id=project_id,
        relationship_id=relationship_id,
    )
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return _to_relationship_response(relationship)


@router.get(
    "/relationships/{relationship_id}",
    response_model=RelationshipRecordResponse,
    dependencies=[read_rate_limit],
)
async def get_relationship_by_id_endpoint(
    relationship_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> RelationshipRecordResponse:
    relationship = await get_relationship_by_id(
        session,
        relationship_id=relationship_id,
    )
    if relationship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Relationship not found")
    return _to_relationship_response(relationship)


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
