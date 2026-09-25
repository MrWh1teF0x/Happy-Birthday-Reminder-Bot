from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from aiogram.types import Message as TgMessage
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import UserRepository, UserSettingRepository
from src.database.models import Base
from src.handlers import router
from src.handlers.reminder_saver import DbReminderSaver
from src.handlers.reminders import (
    ADD_ALL,
    ADD_BACK,
    ADD_CANCEL,
    ADD_NEW,
    add_reminder_handler,
    edit_reminder_hint_handler,
    parse_days,
    parse_time,
    reminder_add_button_handler,
    reminder_all_handler,
    reminder_back_handler,
    reminder_cancel_handler,
    reminder_days_button_handler,
    reminder_days_handler,
    reminder_delete_yes_handler,
    reminder_edit_button_handler,
    reminder_field_handler,
    reminder_time_button_handler,
    reminder_time_handler,
    reminder_toggle_handler,
    reminder_value_handler,
    reminders_list_handler,
)
from src.handlers.reminders import router as reminders_router
from src.handlers.states import AddReminderSG


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


def make_message(text: str) -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    message.text = text
    message.chat.id = 123
    message.bot.delete_message = AsyncMock()
    message.from_user.id = 123
    message.from_user.username = "owner"
    return message


def make_state(data: dict[str, object] | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


def make_callback(data: str, user_id: int = 123) -> MagicMock:
    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.data = data
    callback.from_user.id = user_id
    callback.from_user.username = "owner"
    callback.message = MagicMock(spec=TgMessage)
    callback.message.edit_text = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.answer = AsyncMock()
    object.__setattr__(callback.message, "message_id", 5)
    return callback


async def seed_setting(session: AsyncSession, tg_id: int = 123) -> int:
    setting = await UserSettingRepository(session).create(tg_id)
    return setting.id


async def test_add_reminder_full_flow() -> None:
    async for session in make_session():
        message = make_message("/add_reminder")
        await add_reminder_handler(message, session, AsyncMock())

        assert "Шаг 1 из 2" in message.answer.await_args.args[0]
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 5

        await reminder_days_handler(make_message("3"), make_state())

        state = make_state({"days": 3})
        await reminder_time_handler(make_message("08:30"), session, state)
        state.clear.assert_awaited_once()

        settings = await UserSettingRepository(session).list_by_user(123)
        assert len(settings) == 1
        assert settings[0].notify_days_before == 3
        assert settings[0].notification_time.strftime("%H:%M") == "08:30"


async def test_add_reminder_buttons_flow() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)

        state = make_state()
        callback = make_callback("rem_add:days:7")
        await reminder_days_button_handler(callback, state)
        state.set_state.assert_awaited_once_with(AddReminderSG.waiting_for_time)
        assert "Шаг 2 из 2" in callback.message.edit_text.await_args.args[0]

        state = make_state({"days": 7})
        callback = make_callback("rem_add:time:18:00")
        await reminder_time_button_handler(callback, session, state)
        state.clear.assert_awaited_once()

        settings = await UserSettingRepository(session).list_by_user(123)
        assert len(settings) == 1
        assert settings[0].notification_time.strftime("%H:%M") == "18:00"
        callback.message.delete.assert_awaited_once()
        text = callback.message.answer.await_args.args[0]
        assert "сохранено" in text
        keyboard = callback.message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 1


async def test_add_reminder_dedupe_updates_time() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        await UserSettingRepository(session).create(123, notify_days_before=3)

        state = make_state({"days": 3})
        await reminder_time_handler(make_message("10:00"), session, state)

        settings = await UserSettingRepository(session).list_by_user(123)
        assert len(settings) == 1
        assert settings[0].notification_time.strftime("%H:%M") == "10:00"


async def test_add_reminder_back_returns_to_days() -> None:
    state = AsyncMock()
    callback = make_callback(ADD_BACK)

    await reminder_back_handler(callback, state)

    state.set_state.assert_awaited_once_with(AddReminderSG.waiting_for_days)
    assert "Шаг 1 из 2" in callback.message.edit_text.await_args.args[0]


async def test_add_reminder_cancel() -> None:
    state = make_state({"days": 3})
    callback = make_callback(ADD_CANCEL)

    await reminder_cancel_handler(callback, state)

    state.clear.assert_awaited_once()
    assert "отменено" in callback.message.edit_text.await_args.args[0].lower()


async def test_add_reminder_new_and_all_buttons() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        await seed_setting(session)

        state = AsyncMock()
        callback = make_callback(ADD_NEW)
        await reminder_add_button_handler(callback, session, state)
        state.set_state.assert_awaited_once_with(AddReminderSG.waiting_for_days)

        callback = make_callback(ADD_ALL)
        await reminder_all_handler(callback, session)
        assert "За 7 дн." in callback.message.edit_text.await_args.args[0]


async def test_saver_service_dedupes() -> None:
    from datetime import time

    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        saver = DbReminderSaver(session)

        first = await saver.save_reminder(123, 3, time(9, 0))
        second = await saver.save_reminder(123, 3, time(18, 0))

        assert first.id == second.id
        assert second.notification_time == time(18, 0)
        assert len(await UserSettingRepository(session).list_by_user(123)) == 1


async def test_reminder_days_invalid_deletes_messages() -> None:
    state = make_state({"days_prompt_id": 42})
    message = make_message("много")

    await reminder_days_handler(message, state)

    message.delete.assert_awaited_once()
    message.bot.delete_message.assert_awaited_once_with(123, 42)
    assert "корректное число" in message.answer.await_args.args[0]
    state.set_state.assert_not_awaited()


async def test_reminder_time_invalid_deletes_messages() -> None:
    async for session in make_session():
        state = make_state({"days": 3, "time_prompt_id": 43})
        message = make_message("25:00")

        await reminder_time_handler(message, session, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 43)
        assert "Некорректный формат" in message.answer.await_args.args[0]
        assert await UserSettingRepository(session).list_by_user(123) == []
        state.clear.assert_not_awaited()


async def test_each_step_cleans_previous_messages() -> None:
    async for session in make_session():
        state = make_state({"days_prompt_id": 11})
        message = make_message("3")

        await reminder_days_handler(message, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 11)

        state = make_state({"days": 3, "time_prompt_id": 22})
        message = make_message("08:30")

        await reminder_time_handler(message, session, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 22)


async def test_reminders_list_shows_entries() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        await seed_setting(session)
        message = make_message("/reminders_list")

        await reminders_list_handler(message, session)

        assert "За 7 дн. в 09:00" in message.answer.await_args.args[0]


async def test_reminders_list_empty() -> None:
    async for session in make_session():
        message = make_message("/reminders_list")

        await reminders_list_handler(message, session)

        assert "/add_reminder" in message.answer.await_args.args[0]


async def test_edit_reminder_hint_points_to_list() -> None:
    message = make_message("/edit_reminder")

    await edit_reminder_hint_handler(message)

    assert "/reminders_list" in message.answer.await_args.args[0]


async def test_edit_flow_changes_days() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)

        state = make_state()
        await reminder_edit_button_handler(
            make_callback(f"reminder:edit:{setting_id}"), session, state
        )
        state.set_state.assert_awaited_once()

        state = make_state({"setting_id": setting_id})
        await reminder_field_handler(make_callback(f"redit:{setting_id}:days"), session, state)

        state = make_state({"setting_id": setting_id, "field": "days"})
        message = make_message("1")
        await reminder_value_handler(message, session, state)
        state.clear.assert_awaited_once()

        setting = await UserSettingRepository(session).get(setting_id)
        assert setting is not None and setting.notify_days_before == 1


async def test_toggle_flips_enabled() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)

        await reminder_toggle_handler(make_callback(f"reminder:toggle:{setting_id}"), session)

        setting = await UserSettingRepository(session).get(setting_id)
        assert setting is not None and setting.is_enabled is False


async def test_delete_yes_removes_setting() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)

        await reminder_delete_yes_handler(make_callback(f"rdel_yes:{setting_id}"), session)

        assert await UserSettingRepository(session).get(setting_id) is None


async def test_edit_button_rejects_foreign_setting() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(999)
        setting_id = await seed_setting(session, tg_id=999)
        state = make_state()

        await reminder_edit_button_handler(
            make_callback(f"reminder:edit:{setting_id}"), session, state
        )

        state.set_state.assert_not_awaited()


def test_parse_days() -> None:
    assert parse_days("7") == 7
    assert parse_days("0") == 0
    assert parse_days("366") is None
    assert parse_days("-1") is None
    assert parse_days("много") is None


def test_parse_time() -> None:
    parsed = parse_time("09:00")
    assert parsed is not None and (parsed.hour, parsed.minute) == (9, 0)
    assert parse_time("9:00") is not None
    assert parse_time("25:00") is None
    assert parse_time("утром") is None


def test_reminders_router_is_included() -> None:
    assert reminders_router in router.sub_routers
