import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher
from alembic import command
from alembic.config import Config

from src.config.config import Settings
from src.handlers import router


def run_migrations() -> None:
    command.upgrade(Config(str(Path("alembic.ini").resolve())), "head")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()  # type: ignore[call-arg]  # поля подставляются из окружения/.env
    await asyncio.to_thread(run_migrations)
    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
