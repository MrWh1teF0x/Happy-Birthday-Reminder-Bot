from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock

from pytest import fixture, raises
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import UserRepository
from src.database.models import Base
from src.middlewares import DbSessionMiddleware


@fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def test_middleware_commits_on_success(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    middleware = DbSessionMiddleware(session_factory)

    async def handler(event: Any, data: dict[str, Any]) -> str:
        repo = UserRepository(data["db"])
        await repo.get_or_create(1, username="owner")
        return "ok"

    assert await middleware(handler, AsyncMock(), {}) == "ok"

    async with session_factory() as session:
        assert await UserRepository(session).get_by_tg_id(1) is not None


async def test_middleware_rolls_back_on_error(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    middleware = DbSessionMiddleware(session_factory)

    async def handler(event: Any, data: dict[str, Any]) -> None:
        repo = UserRepository(data["db"])
        await repo.get_or_create(2, username="owner")
        raise RuntimeError("boom")

    with raises(RuntimeError, match="boom"):
        await middleware(handler, AsyncMock(), {})

    async with session_factory() as session:
        assert await UserRepository(session).get_by_tg_id(2) is None
