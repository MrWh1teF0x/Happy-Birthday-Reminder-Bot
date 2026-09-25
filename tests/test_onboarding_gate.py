from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock

from aiogram.types import CallbackQuery, Chat, Message, User
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import UserRepository
from src.database.models import Base
from src.middlewares.onboarding import ONBOARDING_PROMPT, OnboardingMiddleware


async def make_session() -> AsyncIterator[AsyncSession]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as session:
        yield session
    await engine.dispose()


def make_message(text: str) -> Message:
    message = Message(
        message_id=1,
        date=datetime.now(),
        chat=Chat(id=123, type="private"),
        text=text,
        from_user=User(id=123, is_bot=False, first_name="T"),
    )
    # aiogram-типы frozen: подмена метода в обход валидации.
    object.__setattr__(message, "answer", AsyncMock())
    return message


def make_callback(data: str) -> CallbackQuery:
    callback = CallbackQuery(
        id="q1",
        from_user=User(id=123, is_bot=False, first_name="T"),
        chat_instance="inst",
        data=data,
    )
    object.__setattr__(callback, "answer", AsyncMock())
    return callback


async def run_middleware(event: Any, session: AsyncSession) -> AsyncMock:
    handler = AsyncMock(return_value="handled")
    await OnboardingMiddleware()(handler, event, {"db": session})
    return handler


async def test_blocks_command_before_timezone() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        message = make_message("/add_birthday")

        handler = await run_middleware(message, session)

        handler.assert_not_awaited()
        message.answer.assert_awaited_once_with(ONBOARDING_PROMPT)  # type: ignore[attr-defined]


async def test_blocks_unknown_user() -> None:
    async for session in make_session():
        message = make_message("/help")

        handler = await run_middleware(message, session)

        handler.assert_not_awaited()


async def test_allows_start_command() -> None:
    async for session in make_session():
        handler = await run_middleware(make_message("/start"), session)

        handler.assert_awaited_once()


async def test_allows_plain_text() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        handler = await run_middleware(make_message("Europe/Moscow"), session)

        handler.assert_awaited_once()


async def test_allows_timezone_buttons() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        handler = await run_middleware(make_callback("tz:UTC"), session)

        handler.assert_awaited_once()


async def test_blocks_other_buttons_with_alert() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        callback = make_callback("edit_bday:1")

        handler = await run_middleware(callback, session)

        handler.assert_not_awaited()
        callback.answer.assert_awaited_once_with(ONBOARDING_PROMPT, show_alert=True)  # type: ignore[attr-defined]


async def test_allows_commands_after_confirmation() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        await UserRepository(session).set_time_zone(123, "UTC")

        handler = await run_middleware(make_message("/add_birthday"), session)

        handler.assert_awaited_once()
