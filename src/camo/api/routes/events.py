from __future__ import annotations

from hashlib import sha1

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.schemas import EventCreateRequest, EventRecordResponse
from camo.db.queries.characters import get_character_by_id
from camo.db.queries.events import list_events_for_project, upsert_events
from camo.db.queries.projects import get_project

router = APIRouter(tags=["events"])


@router.get("/projects/{project_id}/events", response_model=list[EventRecordResponse], dependencies=[read_rate_limit])
async def list_project_events_endpoint(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> list[EventRecordResponse]:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    events = await list_events_for_project(session, project_id=project_id)
    return [_to_event_response(item) for item in events]


@router.post(
    "/projects/{project_id}/events",
    response_model=EventRecordResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[write_rate_limit],
)
async def create_project_event_endpoint(
    project_id: str,
    payload: EventCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> EventRecordResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    for character_id in payload.participant_character_ids:
        character = await get_character_by_id(session, character_id)
        if character is None or character.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Participant character not found: {character_id}",
            )

    event_id = f"evt_{sha1('|'.join([project_id, payload.title, *payload.source_segments]).encode('utf-8')).hexdigest()[:12]}"
    stored = await upsert_events(
        session,
        [
            {
                "event_id": event_id,
                "project_id": project_id,
                "schema_version": "0.2",
                "title": payload.title,
                "description": payload.description,
                "timeline_pos": payload.timeline_pos,
                "participants": payload.participant_character_ids,
                "location": payload.location,
                "emotion_valence": payload.emotion_valence,
                "source_segments": payload.source_segments,
            }
        ],
    )
    return _to_event_response(stored[0])


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
