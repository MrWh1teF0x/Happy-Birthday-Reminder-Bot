from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database import UserRepository, build_engine, init_db


async def test_init_db_creates_schema_in_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "bot.db"

    engine = build_engine(f"sqlite+aiosqlite:///{db_path}")
    try:
        await init_db(engine)

        assert db_path.exists()

        maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with maker() as session:
            user = await UserRepository(session).get_or_create(1, username="owner")
            await session.commit()

            assert user.tg_id == 1
    finally:
        await engine.dispose()
