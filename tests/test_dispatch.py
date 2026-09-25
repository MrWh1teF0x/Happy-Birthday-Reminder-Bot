"""Сквозной тест: настоящий CallbackQuery через настоящий Dispatcher.

Проверяет всю цепочку: роутинг по F.data, DbSessionMiddleware, FSMContext.
Сеть замокана на уровне Bot.session.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from unittest.mock import AsyncMock

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from pytest import fixture
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import UserRepository
from src.database.models import Base
from src.handlers import router
from src.middlewares import DbSessionMiddleware


@fixture
async def setup() -> AsyncIterator[tuple[Dispatcher, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.middleware(DbSessionMiddleware(maker))
    dispatcher.include_router(router)
    yield dispatcher, maker
    await engine.dispose()


def make_bot() -> Bot:
    bot = Bot(token="123456:" + "A" * 35)
    bot.session = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return bot


def make_callback(data: str) -> CallbackQuery:
    user = User(id=123, is_bot=False, first_name="Тест", username="owner")
    chat = Chat(id=123, type="private")
    message = Message(message_id=1, date=datetime.now(), chat=chat, text="prompt")
    return CallbackQuery(
        id="query-1", from_user=user, chat_instance="inst", data=data, message=message
    )


async def test_timezone_button_dispatch_end_to_end(
    setup: tuple[Dispatcher, async_sessionmaker[AsyncSession]],
) -> None:
    dispatcher, maker = setup
    bot = make_bot()

    await dispatcher.feed_update(
        bot, Update(update_id=1, callback_query=make_callback("tz:Asia/Almaty"))
    )

    async with maker() as session:
        user = await UserRepository(session).get_by_tg_id(123)
    assert user is not None
    assert user.time_zone == "Asia/Almaty"
    bot.session.assert_awaited()  # type: ignore[attr-defined]
