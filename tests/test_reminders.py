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
from src.handlers.reminders import (
    add_reminder_handler,
    edit_reminder_hint_handler,
    parse_days,
    parse_time,
    reminder_days_handler,
    reminder_delete_yes_handler,
    reminder_edit_button_handler,
    reminder_field_handler,
    reminder_time_handler,
    reminder_toggle_handler,
    reminder_value_handler,
    reminders_list_handler,
)
from src.handlers.reminders import router as reminders_router


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
    message.text = text
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
    callback.message = MagicMock(spec=TgMessage)
    callback.message.edit_text = AsyncMock()
    return callback


async def seed_setting(session: AsyncSession, tg_id: int = 123) -> int:
    setting = await UserSettingRepository(session).create(tg_id)
    return setting.id


async def test_add_reminder_full_flow() -> None:
    async for session in make_session():
        await add_reminder_handler(make_message("/add_reminder"), session, AsyncMock())

        await reminder_days_handler(make_message("3"), make_state())

        state = make_state({"days": 3})
        await reminder_time_handler(make_message("08:30"), session, state)
        state.clear.assert_awaited_once()

        settings = await UserSettingRepository(session).list_by_user(123)
        assert len(settings) == 1
        assert settings[0].notify_days_before == 3
        assert settings[0].notification_time.strftime("%H:%M") == "08:30"


async def test_reminder_days_invalid_stays_in_state() -> None:
    state = AsyncMock()

    await reminder_days_handler(make_message("много"), state)

    state.set_state.assert_not_awaited()


async def test_reminder_time_invalid_stays_in_state() -> None:
    async for session in make_session():
        state = make_state({"days": 3})

        await reminder_time_handler(make_message("25:00"), session, state)

        assert await UserSettingRepository(session).list_by_user(123) == []
        state.clear.assert_not_awaited()


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
