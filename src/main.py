import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config.config import Settings
from src.database import build_engine
from src.handlers import router
from src.handlers.commands import setup_commands
from src.middlewares import DbSessionMiddleware, OnboardingMiddleware

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    command.upgrade(Config(str(Path("alembic.ini").resolve())), "head")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()  # type: ignore[call-arg]  # поля подставляются из окружения/.env
    await asyncio.to_thread(run_migrations)
    # alembic.ini через fileConfig опускает root-уровень до WARN —
    # возвращаем INFO, иначе после миграций в логах тишина.
    logging.getLogger().setLevel(logging.INFO)
    logger.info("Migrations done, connecting to Telegram...")
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher(storage=MemoryStorage())
    engine = build_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    dispatcher.update.middleware(DbSessionMiddleware(session_factory))
    dispatcher.update.middleware(OnboardingMiddleware())
    dispatcher.include_router(router)
    try:
        await setup_commands(bot)
        logger.info("Bot started, polling for updates...")
        await dispatcher.start_polling(bot)
    finally:
        await engine.dispose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
