from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import PersonRepository
from src.database.models import Base
from src.handlers import router
from src.handlers.birthday_saver import BirthdayDraft, DbBirthdaySaver
from src.handlers.birthdays import (
    ADD_AGAIN,
    ADD_CANCEL,
    ADD_LIST,
    ADD_SKIP_NOTE,
    add_birthday_handler,
    birthday_again_handler,
    birthday_cancel_handler,
    birthday_date_handler,
    birthday_delete_no_handler,
    birthday_delete_yes_handler,
    birthday_edit_button_handler,
    birthday_field_handler,
    birthday_list_button_handler,
    birthday_name_handler,
    birthday_note_handler,
    birthday_skip_note_handler,
    birthday_value_handler,
    birthdays_list_handler,
    edit_birthday_hint_handler,
    format_birthday,
    format_birthday_long,
    parse_birthday_date,
)
from src.handlers.birthdays import router as birthdays_router
from src.handlers.states import AddBirthdaySG


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


async def test_add_birthday_full_flow_with_note() -> None:
    async for session in make_session():
        await add_birthday_handler(make_message("/add_birthday"), session, AsyncMock())

        state = make_state()
        message = make_message("Иван")
        await birthday_name_handler(message, state)
        state.set_state.assert_awaited_once_with(AddBirthdaySG.waiting_for_date)
        assert "Шаг 2 из 3" in message.answer.await_args.args[0]
        assert "Иван" in message.answer.await_args.args[0]

        state = make_state({"fullname": "Иван"})
        message = make_message("12.09.1995")
        await birthday_date_handler(message, state)
        state.set_state.assert_awaited_once_with(AddBirthdaySG.waiting_for_note)
        assert "Шаг 3 из 3" in message.answer.await_args.args[0]

        state = make_state({"fullname": "Иван", "day": 12, "month": 9, "year": 1995})
        message = make_message("Любит книги про историю")
        await birthday_note_handler(message, session, state)
        state.clear.assert_awaited_once()

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert (persons[0].fullname, persons[0].birth_day, persons[0].birth_month) == (
            "Иван",
            12,
            9,
        )
        assert persons[0].birth_year == 1995
        assert persons[0].notes == "Любит книги про историю"
        text = message.answer.await_args.args[0]
        assert "успешно сохранен" in text
        assert "12 сентября 1995" in text
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 2


async def test_add_birthday_skip_note() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Анна", "day": 1, "month": 3, "year": None})
        callback = make_callback(ADD_SKIP_NOTE)

        await birthday_skip_note_handler(callback, session, state)
        state.clear.assert_awaited_once()

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert persons[0].notes is None
        text = callback.message.edit_text.await_args.args[0]
        assert "1 марта" in text
        assert "нет" in text


async def test_add_birthday_cancel_clears_state() -> None:
    state = make_state({"fullname": "Иван"})
    callback = make_callback(ADD_CANCEL)

    await birthday_cancel_handler(callback, state)

    state.clear.assert_awaited_once()
    assert "отменено" in callback.message.edit_text.await_args.args[0].lower()


async def test_add_birthday_again_restarts_flow() -> None:
    state = AsyncMock()
    callback = make_callback(ADD_AGAIN)

    await birthday_again_handler(callback, state)

    state.set_state.assert_awaited_once_with(AddBirthdaySG.waiting_for_name)
    assert "Шаг 1 из 3" in callback.message.edit_text.await_args.args[0]


async def test_add_birthday_list_button_shows_list() -> None:
    async for session in make_session():
        await PersonRepository(session).create(123, fullname="Иван", birth_day=12, birth_month=5)
        callback = make_callback(ADD_LIST)

        await birthday_list_button_handler(callback, session)

        assert "Иван" in callback.message.edit_text.await_args.args[0]


async def test_birthday_date_without_year() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Анна"})

        await birthday_date_handler(make_message("01.03"), state)

        assert await PersonRepository(session).list_by_owner(123) == []
        state.set_state.assert_awaited_once_with(AddBirthdaySG.waiting_for_note)


async def test_birthday_date_invalid_stays_in_state() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Иван"})
        message = make_message("31.02")

        await birthday_date_handler(message, state)

        assert "Некорректный формат" in message.answer.await_args.args[0]
        assert await PersonRepository(session).list_by_owner(123) == []
        state.set_state.assert_not_awaited()


async def test_birthday_name_empty_stays_in_state() -> None:
    state = AsyncMock()

    await birthday_name_handler(make_message("   "), state)

    state.set_state.assert_not_awaited()


def test_parse_birthday_date() -> None:
    assert parse_birthday_date("12.09.1995") == (12, 9, 1995)
    assert parse_birthday_date("12/09/1995") == (12, 9, 1995)
    assert parse_birthday_date("12-09-1995") == (12, 9, 1995)
    assert parse_birthday_date("12 09 1995") == (12, 9, 1995)
    assert parse_birthday_date("1.3") == (1, 3, None)
    assert parse_birthday_date("29.02") == (29, 2, None)
    assert parse_birthday_date("29.02.2023") is None
    assert parse_birthday_date("31.02") is None
    assert parse_birthday_date("99.99") is None
    assert parse_birthday_date("32.01") is None
    assert parse_birthday_date("12.13") is None
    assert parse_birthday_date("завтра") is None


def test_format_birthday_long() -> None:
    assert format_birthday_long(12, 9, 1995) == "12 сентября 1995"
    assert format_birthday_long(1, 3, None) == "1 марта"
    assert format_birthday_long(29, 2, None) == "29 февраля"


async def test_saver_service_stores_draft() -> None:
    async for session in make_session():
        draft = BirthdayDraft(fullname="Иван", day=12, month=9, year=1995, note="Книги")

        await DbBirthdaySaver(session).save_birthday(123, draft)

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert persons[0].notes == "Книги"


def test_birthdays_router_is_included() -> None:
    assert birthdays_router in router.sub_routers


def make_callback(data: str, user_id: int = 123) -> MagicMock:
    from aiogram.types import Message as TgMessage

    callback = MagicMock()
    callback.answer = AsyncMock()
    callback.data = data
    callback.from_user.id = user_id
    callback.message = MagicMock(spec=TgMessage)
    callback.message.edit_text = AsyncMock()
    return callback


async def seed_person(session: AsyncSession, tg_id: int = 123) -> int:
    person = await PersonRepository(session).create(
        tg_id, fullname="Иван", birth_day=12, birth_month=5, birth_year=2000
    )
    return person.id


async def test_birthdays_list_empty() -> None:
    async for session in make_session():
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session)

        text = message.answer.await_args.args[0]
        assert "Здесь пока ничего нет" in text
        assert "/add_birthday" in text


async def test_birthdays_list_shows_entries_with_buttons() -> None:
    async for session in make_session():
        await seed_person(session)
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session)

        text = message.answer.await_args.args[0]
        assert "Иван — 12.05.2000" in text
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 1


async def test_edit_birthday_hint_points_to_list() -> None:
    message = make_message("/edit_birthday")

    await edit_birthday_hint_handler(message)

    assert "/birthdays_list" in message.answer.await_args.args[0]


async def test_edit_flow_changes_fullname() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        state = make_state()
        callback = make_callback(f"birthday:edit:{person_id}")
        await birthday_edit_button_handler(callback, session, state)
        state.set_state.assert_awaited_once()
        assert callback.message.edit_text.await_count == 1

        state = make_state({"person_id": person_id})
        callback = make_callback(f"bedit:{person_id}:fullname")
        await birthday_field_handler(callback, session, state)

        state = make_state({"person_id": person_id, "field": "fullname"})
        message = make_message("Пётр")
        await birthday_value_handler(message, session, state)
        state.clear.assert_awaited_once()

        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.fullname == "Пётр"


async def test_edit_flow_rejects_bad_date() -> None:
    async for session in make_session():
        person_id = await seed_person(session)
        state = make_state({"person_id": person_id, "field": "date"})

        await birthday_value_handler(make_message("30.02"), session, state)

        state.clear.assert_not_awaited()
        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.birth_day == 12


async def test_edit_button_rejects_foreign_person() -> None:
    async for session in make_session():
        person_id = await seed_person(session, tg_id=999)
        state = make_state()

        callback = make_callback(f"birthday:edit:{person_id}")
        await birthday_edit_button_handler(callback, session, state)

        state.set_state.assert_not_awaited()


async def test_delete_yes_removes_person() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        await birthday_delete_yes_handler(make_callback(f"bdel_yes:{person_id}"), session)

        assert await PersonRepository(session).get(person_id) is None


async def test_delete_no_keeps_person() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        await birthday_delete_no_handler(make_callback(f"bdel_no:{person_id}"), session)

        assert await PersonRepository(session).get(person_id) is not None


def test_format_birthday_without_year() -> None:
    person = MagicMock()
    person.fullname = "Анна"
    person.birth_day = 1
    person.birth_month = 3
    person.birth_year = None

    assert format_birthday(person) == "Анна — 01.03"
