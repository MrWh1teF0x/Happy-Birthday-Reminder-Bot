import asyncio
import logging

from aiogram import Bot, Dispatcher

from src.config import Settings
from src.database import build_engine, init_db
from src.handlers import router


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()  # type: ignore[call-arg]  # поля подставляются из окружения/.env
    engine = build_engine(settings.database_url)
    await init_db(engine)
    try:
        bot = Bot(token=settings.bot_token)
        dispatcher = Dispatcher()
        dispatcher.include_router(router)
        await dispatcher.start_polling(bot)
    finally:
        await engine.dispose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
