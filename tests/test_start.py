from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import UserRepository, UserSettingRepository
from src.database.models import Base
from src.handlers import router, start_handler
from src.handlers.start import router as start_router
from src.handlers.states import TimezoneStates
from src.handlers.timezone import (
    edit_utc_handler,
    is_valid_timezone,
    save_timezone_and_seed_reminder,
    timezone_button_handler,
    timezone_text_handler,
)
from src.handlers.timezone import router as timezone_router


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


def make_message(text: str = "/start") -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock()
    message.text = text
    message.from_user.id = 123
    message.from_user.username = "owner"
    message.from_user.full_name = "Тест"
    return message


async def test_start_handler_greets_user_by_name() -> None:
    async for session in make_session():
        message = make_message()
        state = AsyncMock()

        await start_handler(message, session, state)

        texts = [call.args[0] for call in message.answer.await_args_list]
        assert any("Тест" in text for text in texts)


async def test_start_handler_creates_user_and_asks_timezone() -> None:
    async for session in make_session():
        message = make_message()
        state = AsyncMock()

        await start_handler(message, session, state)

        state.set_state.assert_awaited_once_with(TimezoneStates.waiting_for_timezone)
        assert await UserRepository(session).get_by_tg_id(123) is not None
        assert message.answer.await_count == 2
        keyboard = message.answer.await_args_list[1].kwargs["reply_markup"]
        assert keyboard.inline_keyboard


async def test_timezone_button_saves_zone_and_seeds_default_reminder() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.data = "tz:Europe/Moscow"
        callback.from_user.id = 123
        callback.message.edit_text = AsyncMock()
        state = AsyncMock()

        await timezone_button_handler(callback, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "Europe/Moscow"
        reminders = await UserSettingRepository(session).list_by_user(123)
        assert len(reminders) == 1
        assert reminders[0].notify_days_before == 7
        state.clear.assert_awaited_once()


async def test_timezone_text_rejects_unknown_zone() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        message = make_message("Mars/Olympus")
        state = AsyncMock()

        await timezone_text_handler(message, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "UTC"
        state.clear.assert_not_awaited()


async def test_timezone_text_accepts_iana_name() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        message = make_message("Asia/Almaty")
        state = AsyncMock()

        await timezone_text_handler(message, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "Asia/Almaty"
        state.clear.assert_awaited_once()


def test_is_valid_timezone() -> None:
    assert is_valid_timezone("Europe/Moscow") is True
    assert is_valid_timezone("Not/AZone") is False


async def test_save_timezone_requires_registered_user() -> None:
    from pytest import raises

    async for session in make_session():
        with raises(ValueError, match="not registered"):
            await save_timezone_and_seed_reminder(session, 999, "UTC")


async def test_edit_utc_shows_current_zone_and_sets_state() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123, time_zone="Asia/Almaty")
        message = make_message("/edit_utc")
        state = AsyncMock()

        await edit_utc_handler(message, session, state)

        state.set_state.assert_awaited_once_with(TimezoneStates.waiting_for_timezone)
        prompt = message.answer.await_args.args[0]
        assert "Asia/Almaty" in prompt


def test_routers_are_included_in_root_router() -> None:
    assert start_router in router.sub_routers
    assert timezone_router in router.sub_routers
