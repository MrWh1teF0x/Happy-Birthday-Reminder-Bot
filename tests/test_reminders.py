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
    format_days_full,
    parse_days,
    parse_time,
    reminder_add_button_handler,
    reminder_all_handler,
    reminder_back_handler,
    reminder_cancel_handler,
    reminder_days_button_handler,
    reminder_days_handler,
    reminder_delete_button_handler,
    reminder_delete_no_handler,
    reminder_delete_yes_handler,
    reminder_time_button_handler,
    reminder_time_edit_button_handler,
    reminder_time_handler,
    reminder_value_handler,
    reminders_list_handler,
    reminders_page_handler,
    utc_label,
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
    message.bot.edit_message_text = AsyncMock()
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

        state = make_state()
        callback = make_callback(ADD_NEW)
        await reminder_add_button_handler(callback, session, state)
        state.set_state.assert_awaited_once_with(AddReminderSG.waiting_for_days)

        callback = make_callback(ADD_ALL)
        await reminder_all_handler(callback, session, make_state())
        assert "Настройки напоминаний" in callback.message.edit_text.await_args.args[0]


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


async def test_reminder_days_invalid_warns_on_prompt() -> None:
    state = make_state({"days_prompt_id": 42})
    message = make_message("много")

    await reminder_days_handler(message, state)

    message.delete.assert_awaited_once()
    message.answer.assert_not_awaited()
    edited = message.bot.edit_message_text.await_args
    assert edited.kwargs["message_id"] == 42
    assert edited.args[0].startswith("⚠️")
    assert "Шаг 1 из 2" in edited.args[0]
    keyboard = edited.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 5
    state.set_state.assert_not_awaited()


async def test_reminder_time_invalid_warns_on_prompt() -> None:
    async for session in make_session():
        state = make_state({"days": 3, "time_prompt_id": 43})
        message = make_message("25:00")

        await reminder_time_handler(message, session, state)

        message.delete.assert_awaited_once()
        message.answer.assert_not_awaited()
        edited = message.bot.edit_message_text.await_args
        assert edited.kwargs["message_id"] == 43
        assert edited.args[0].startswith("⚠️")
        assert "Шаг 2 из 2" in edited.args[0]
        keyboard = edited.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 3
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


async def test_reminders_list_empty() -> None:
    async for session in make_session():
        message = make_message("/reminders_list")

        await reminders_list_handler(message, session, AsyncMock())

        assert "нет настроенных напоминаний" in message.answer.await_args.args[0]


async def test_reminders_list_card_page() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123, time_zone="Europe/Moscow")
        await seed_setting(session)
        message = make_message("/reminders_list")

        await reminders_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert "Настройки напоминаний" in text
        assert "Всего: 1, UTC+3" in text
        assert "1️⃣" in text
        assert "За 7 дней" in text
        assert "отправка в 09:00" in text
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 1
        row = keyboard.inline_keyboard[0]
        assert row[0].text == "⏰ Изменить время (7 дн)"
        assert row[1].text == "🗑 Удалить"


async def test_reminders_pagination() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        for days in (0, 1, 3, 5, 7, 14):
            await UserSettingRepository(session).create(123, notify_days_before=days)
        message = make_message("/reminders_list")
        state = AsyncMock()

        await reminders_list_handler(message, session, state)

        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 6
        nav = keyboard.inline_keyboard[5]
        assert [button.text for button in nav] == ["1 / 2", "Вперед ➡️"]

        callback = make_callback("rem_page:2")
        await reminders_page_handler(callback, session, state)

        rows = callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        assert len(rows) == 2
        assert [button.text for button in rows[-1]] == ["⬅️ Назад", "2 / 2"]


async def test_reminders_sorted_chronologically() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        for days in (1, 7, 0, 3):
            await UserSettingRepository(session).create(123, notify_days_before=days)
        message = make_message("/reminders_list")

        await reminders_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert (
            text.index("За 7 дней")
            < text.index("За 3 дня")
            < text.index("За 1 день")
            < text.index("В день праздника")
        )


async def test_edit_reminder_hint_points_to_list() -> None:
    message = make_message("/edit_reminder")

    await edit_reminder_hint_handler(message)

    assert "/reminders_list" in message.answer.await_args.args[0]


async def test_time_edit_flow_changes_time() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)

        state = make_state()
        callback = make_callback(f"edit_rem:{setting_id}")
        await reminder_time_edit_button_handler(callback, session, state)
        state.set_state.assert_awaited_once()
        assert "09:00" in callback.message.edit_text.await_args.args[0]

        state = make_state({"setting_id": setting_id, "field": "time"})
        message = make_message("10:00")
        await reminder_value_handler(message, session, state)
        state.clear.assert_awaited_once()

        setting = await UserSettingRepository(session).get(setting_id)
        assert setting is not None
        assert setting.notification_time.strftime("%H:%M") == "10:00"


async def test_time_edit_rejects_bad_time() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)
        state = make_state({"setting_id": setting_id, "field": "time"})

        await reminder_value_handler(make_message("утром"), session, state)

        state.clear.assert_not_awaited()


async def test_time_edit_rejects_foreign_setting() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(999)
        setting_id = await seed_setting(session, tg_id=999)
        state = make_state()

        await reminder_time_edit_button_handler(
            make_callback(f"edit_rem:{setting_id}"), session, state
        )

        state.set_state.assert_not_awaited()


async def test_delete_confirm_and_remove() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)
        state = make_state({"rem_page": 1})

        callback = make_callback(f"del_rem:{setting_id}")
        await reminder_delete_button_handler(callback, session)

        text = callback.message.edit_text.await_args.args[0]
        assert "Вы уверены" in text
        keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "✅ Да, удалить"

        callback = make_callback(f"confirm_del_rem:{setting_id}")
        await reminder_delete_yes_handler(callback, session, state)

        assert await UserSettingRepository(session).get(setting_id) is None
        assert "успешно удалена" in callback.answer.await_args.args[0].lower()
        assert "нет настроенных напоминаний" in callback.message.edit_text.await_args.args[0]


async def test_delete_cancel_returns_to_list() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        setting_id = await seed_setting(session)
        state = make_state({"rem_page": 1})
        callback = make_callback("cancel_del_rem")

        await reminder_delete_no_handler(callback, session, state)

        assert await UserSettingRepository(session).get(setting_id) is not None
        assert "Настройки напоминаний" in callback.message.edit_text.await_args.args[0]


async def test_delete_last_on_page_returns_to_previous() -> None:
    async for session in make_session():
        await UserRepository(session).get_or_create(123)
        ids = []
        for days in (0, 1, 3, 5, 7, 14):
            setting = await UserSettingRepository(session).create(123, notify_days_before=days)
            ids.append(setting.id)
        state = make_state({"rem_page": 2})

        callback = make_callback(f"confirm_del_rem:{ids[5]}")
        await reminder_delete_yes_handler(callback, session, state)

        rows = callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        assert len(rows) == 5


def test_format_days_full() -> None:
    assert format_days_full(0) == "В день праздника"
    assert format_days_full(1) == "За 1 день"
    assert format_days_full(3) == "За 3 дня"
    assert format_days_full(7) == "За 7 дней"


def test_utc_label() -> None:
    assert utc_label("Europe/Moscow") == "UTC+3"
    assert utc_label("Asia/Kamchatka") == "UTC+12"
    assert utc_label("Nope/Nowhere") == "UTC"


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
