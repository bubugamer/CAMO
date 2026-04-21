from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    return create_async_engine(database_url, echo=echo)


def create_session_factory(
    bind: str | AsyncEngine,
    *,
    echo: bool = False,
    expire_on_commit: bool = False,
) -> async_sessionmaker[AsyncSession]:
    engine = bind if isinstance(bind, AsyncEngine) else create_engine(bind, echo=echo)
    return async_sessionmaker(engine, expire_on_commit=expire_on_commit)
