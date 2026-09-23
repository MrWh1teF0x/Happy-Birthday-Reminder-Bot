"""Создание движка БД и инициализация схемы."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from src.database.models import Base


def build_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite") and ":memory:" not in database_url:
        db_path = database_url.rsplit("///", 1)[-1]
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_async_engine(database_url, pool_pre_ping=True)


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
