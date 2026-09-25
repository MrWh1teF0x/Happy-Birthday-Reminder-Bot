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
from src.handlers.keyboards import TIMEZONE_CALLBACK_PREFIX, build_timezone_keyboard
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
    message.delete = AsyncMock()
    message.text = text
    message.chat.id = 123
    message.bot.delete_message = AsyncMock()
    message.from_user.id = 123
    message.from_user.username = "owner"
    message.from_user.full_name = "Тест"
    return message


def make_state(data: dict[str, object] | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


async def test_start_handler_greets_user_by_name() -> None:
    async for session in make_session():
        message = make_message()
        state = AsyncMock()

        await start_handler(message, session, state)

        texts = [call.args[0] for call in message.answer.await_args_list]
        assert any("Тест" in text for text in texts)
        assert any("главный по праздникам" in text for text in texts)
        assert any("Давай настроим бота под тебя" in text for text in texts)


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
    from aiogram.types import Message as TgMessage

    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.data = "tz:Europe/Moscow"
        callback.from_user.id = 123
        callback.from_user.username = "owner"
        callback.message = MagicMock(spec=TgMessage)
        callback.message.delete = AsyncMock()
        callback.message.answer = AsyncMock()
        state = AsyncMock()

        await timezone_button_handler(callback, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "Europe/Moscow"
        reminders = await UserSettingRepository(session).list_by_user(123)
        assert len(reminders) == 1
        assert reminders[0].notify_days_before == 7
        state.clear.assert_awaited_once()
        callback.message.delete.assert_awaited_once()


async def test_timezone_text_rejects_unknown_zone() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        message = make_message("Mars/Olympus")
        state = AsyncMock()

        await timezone_text_handler(message, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "UTC"
        state.clear.assert_not_awaited()


async def test_first_choice_shows_confirm_and_help() -> None:
    from aiogram.types import Message as TgMessage

    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.data = "tz:Europe/Moscow"
        callback.from_user.id = 123
        callback.from_user.username = "owner"
        callback.message = MagicMock(spec=TgMessage)
        callback.message.delete = AsyncMock()
        callback.message.answer = AsyncMock()
        state = AsyncMock()

        await timezone_button_handler(callback, session, state)

        texts = [call.args[0] for call in callback.message.answer.await_args_list]
        assert any("успешно выбран" in text for text in texts)
        assert any("/add_birthday" in text for text in texts)


async def test_second_choice_shows_changed_without_help() -> None:
    from aiogram.types import Message as TgMessage

    async for session in make_session():
        user = await UserRepository(session).get_or_create(123)
        await UserRepository(session).set_time_zone(123, "UTC")
        user.help_shown = True
        await session.flush()
        callback = MagicMock()
        callback.answer = AsyncMock()
        callback.data = "tz:Europe/Moscow"
        callback.from_user.id = 123
        callback.from_user.username = "owner"
        callback.message = MagicMock(spec=TgMessage)
        callback.message.delete = AsyncMock()
        callback.message.answer = AsyncMock()
        state = AsyncMock()

        await timezone_button_handler(callback, session, state)

        texts = [call.args[0] for call in callback.message.answer.await_args_list]
        assert any("успешно изменён" in text for text in texts)
        assert all("/add_birthday" not in text for text in texts)


async def test_timezone_text_accepts_iana_name() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        message = make_message("Asia/Almaty")
        state = make_state({"tz_prompt_id": 42})

        await timezone_text_handler(message, session, state)

        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.time_zone == "Asia/Almaty"
        state.clear.assert_awaited_once()
        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 42)


async def test_repeated_start_shows_about_only() -> None:
    async for session in make_session():
        user = await UserRepository(session).get_or_create(123)
        await UserRepository(session).set_time_zone(123, "UTC")
        user.help_shown = True
        await session.flush()
        message = make_message()
        state = AsyncMock()

        await start_handler(message, session, state)

        state.set_state.assert_not_awaited()
        assert message.answer.await_count == 1
        text = message.answer.await_args.args[0]
        assert "днях рождения" in text


async def test_repeated_start_shows_help_once_for_grandfathered() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        await UserRepository(session).set_time_zone(123, "UTC")

        message = make_message()
        await start_handler(message, session, AsyncMock())
        assert message.answer.await_count == 2
        assert "/add_birthday" in message.answer.await_args_list[1].args[0]

        message = make_message()
        await start_handler(message, session, AsyncMock())
        assert message.answer.await_count == 1


async def test_maybe_show_help_only_once() -> None:
    from src.handlers.help import maybe_show_help

    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        send = AsyncMock()

        await maybe_show_help(session, 123, send)
        await maybe_show_help(session, 123, send)

        send.assert_awaited_once()
        user = await UserRepository(session).get_by_tg_id(123)
        assert user is not None and user.help_shown is True


def test_is_valid_timezone() -> None:
    assert is_valid_timezone("Europe/Moscow") is True
    assert is_valid_timezone("Not/AZone") is False


async def test_save_timezone_registers_missing_user() -> None:
    async for session in make_session():
        await save_timezone_and_seed_reminder(session, 999, "UTC")

        user = await UserRepository(session).get_by_tg_id(999)
        assert user is not None and user.time_zone == "UTC"


async def test_edit_utc_shows_current_zone_and_sets_state() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123, time_zone="Asia/Almaty")
        message = make_message("/edit_utc")
        state = AsyncMock()

        await edit_utc_handler(message, session, state)

        state.set_state.assert_awaited_once_with(TimezoneStates.waiting_for_timezone)
        prompt = message.answer.await_args.args[0]
        assert "Asia/Almaty" in prompt


def test_timezone_keyboard_covers_all_russian_utc_offsets() -> None:
    keyboard = build_timezone_keyboard()
    assert len(keyboard.inline_keyboard) == 11
    zones = [
        (button.callback_data or "").removeprefix(TIMEZONE_CALLBACK_PREFIX)
        for row in keyboard.inline_keyboard
        for button in row
    ]
    assert all(is_valid_timezone(zone) for zone in zones)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels[0].startswith("MSK-1 (UTC+2)")
    assert labels[-1].startswith("MSK+9 (UTC+12)")
    assert any("Калининград" in label for label in labels)
    assert any("Петропавловск-Камчатский" in label for label in labels)


def test_routers_are_included_in_root_router() -> None:
    assert start_router in router.sub_routers
    assert timezone_router in router.sub_routers
