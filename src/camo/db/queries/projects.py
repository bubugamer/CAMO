from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from camo.db.models import Project


async def create_project(session: AsyncSession, project: Project) -> Project:
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project | None:
    return await session.get(Project, project_id)


async def list_projects(session: AsyncSession, limit: int = 20) -> list[Project]:
    stmt = select(Project).order_by(Project.updated_at.desc(), Project.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())
