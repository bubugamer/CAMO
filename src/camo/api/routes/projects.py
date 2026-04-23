from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from camo.api.deps import get_db_session
from camo.api.rate_limit import read_rate_limit, write_rate_limit
from camo.core.schemas import ProjectCreateRequest, ProjectResponse
from camo.db.models import Project
from camo.db.queries.projects import create_project, get_project, list_projects

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED, dependencies=[write_rate_limit])
async def create_project_endpoint(
    payload: ProjectCreateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    project = Project(
        project_id=f"proj_{uuid4().hex[:12]}",
        tenant_id=payload.tenant_id,
        name=payload.name,
        description=payload.description,
        config=payload.config,
    )
    created = await create_project(session, project)
    return ProjectResponse.model_validate(created)


@router.get("", response_model=list[ProjectResponse], dependencies=[read_rate_limit])
async def list_projects_endpoint(
    session: AsyncSession = Depends(get_db_session),
) -> list[ProjectResponse]:
    projects = await list_projects(session)
    return [ProjectResponse.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectResponse, dependencies=[read_rate_limit])
async def get_project_endpoint(
    project_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> ProjectResponse:
    project = await get_project(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectResponse.model_validate(project)
