from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from camo.models.adapter import ModelAdapter
from camo.runtime.session_store import SessionStore


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_model_adapter(request: Request) -> ModelAdapter:
    return request.app.state.model_adapter


def get_session_store(request: Request) -> SessionStore:
    return request.app.state.session_store
