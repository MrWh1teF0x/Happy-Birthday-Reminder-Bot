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
    CANCEL_EDIT,
    add_birthday_handler,
    birthday_again_handler,
    birthday_cancel_handler,
    birthday_clear_note_handler,
    birthday_date_handler,
    birthday_delete_button_handler,
    birthday_delete_no_handler,
    birthday_delete_yes_handler,
    birthday_edit_button_handler,
    birthday_edit_cancel_handler,
    birthday_edit_field_handler,
    birthday_list_button_handler,
    birthday_name_handler,
    birthday_new_date_handler,
    birthday_new_name_handler,
    birthday_new_note_handler,
    birthday_note_handler,
    birthday_skip_note_handler,
    birthdays_list_handler,
    birthdays_page_handler,
    format_birthday,
    format_birthday_long,
    parse_birthday_date,
)
from src.handlers.birthdays import router as birthdays_router
from src.handlers.states import AddBirthdaySG, EditBirthdaySG


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
        state = make_state(
            {"fullname": "Анна", "day": 1, "month": 3, "year": None, "note_prompt_id": 7}
        )
        callback = make_callback(ADD_SKIP_NOTE)

        await birthday_skip_note_handler(callback, session, state)
        state.clear.assert_awaited_once()

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert persons[0].notes is None
        callback.message.delete.assert_awaited_once()
        text = callback.message.answer.await_args.args[0]
        assert "1 марта" in text
        assert "нет" in text


async def test_add_birthday_cancel_clears_state() -> None:
    state = make_state({"fullname": "Иван"})
    callback = make_callback(ADD_CANCEL)

    await birthday_cancel_handler(callback, state)

    state.clear.assert_awaited_once()
    assert "отменено" in callback.message.edit_text.await_args.args[0].lower()
    keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
    assert keyboard.inline_keyboard[0][0].text == "➕ Начать заново"


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

        await birthday_list_button_handler(callback, session, make_state())

        assert "Иван" in callback.message.edit_text.await_args.args[0]


async def test_birthday_date_without_year() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Анна"})

        await birthday_date_handler(make_message("01.03"), state)

        assert await PersonRepository(session).list_by_owner(123) == []
        state.set_state.assert_awaited_once_with(AddBirthdaySG.waiting_for_note)


async def test_birthday_date_invalid_warns_on_prompt() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Иван", "date_prompt_id": 42})
        message = make_message("31.02")

        await birthday_date_handler(message, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_not_awaited()
        message.answer.assert_not_awaited()
        edited = message.bot.edit_message_text.await_args
        assert edited.kwargs["chat_id"] == 123
        assert edited.kwargs["message_id"] == 42
        assert edited.args[0].startswith("⚠️")
        assert "Шаг 2 из 3" in edited.args[0]
        assert "Иван" in edited.args[0]
        keyboard = edited.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "❌ Отмена"
        assert await PersonRepository(session).list_by_owner(123) == []
        state.set_state.assert_not_awaited()


async def test_each_step_cleans_previous_messages() -> None:
    async for session in make_session():
        state = make_state({"name_prompt_id": 11})
        message = make_message("Иван")

        await birthday_name_handler(message, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 11)

        state = make_state({"fullname": "Иван", "date_prompt_id": 22})
        message = make_message("12.09.1995")

        await birthday_date_handler(message, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 22)

        state = make_state(
            {"fullname": "Иван", "day": 12, "month": 9, "year": 1995, "note_prompt_id": 33}
        )
        message = make_message("Книги")

        await birthday_note_handler(message, session, state)

        message.delete.assert_awaited_once()
        message.bot.delete_message.assert_awaited_once_with(123, 33)


async def test_birthday_name_stores_date_prompt_id() -> None:
    state = make_state()

    await birthday_name_handler(make_message("Иван"), state)

    updated = {}
    for call in state.update_data.await_args_list:
        updated.update(call.kwargs)
    assert updated.get("fullname") == "Иван"
    assert "date_prompt_id" in updated


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
    callback.message.delete = AsyncMock()
    callback.message.answer = AsyncMock()
    object.__setattr__(callback.message, "message_id", 5)
    return callback


async def seed_person(session: AsyncSession, tg_id: int = 123) -> int:
    person = await PersonRepository(session).create(
        tg_id, fullname="Иван", birth_day=12, birth_month=5, birth_year=2000
    )
    return person.id


async def test_birthdays_list_empty() -> None:
    async for session in make_session():
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert "Ваша база дней рождения пока пуста" in text


async def test_birthdays_list_card_page() -> None:
    async for session in make_session():
        await seed_person(session)
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert "Список дней рождения (всего: 1)" in text
        assert "1. Иван" in text
        assert "12 мая" in text
        assert "Исполнится" in text
        assert "───" not in text  # разделитель только между карточками
        assert "Кнопки управления" in text
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 1
        row = keyboard.inline_keyboard[0]
        assert row[0].text == "✏️ Иван"
        assert row[1].text == "🗑 Иван"


async def test_birthdays_pagination() -> None:
    async for session in make_session():
        for i in range(6):
            await PersonRepository(session).create(
                123, fullname=f"Друг{i}", birth_day=1, birth_month=1
            )
        message = make_message("/birthdays_list")
        state = AsyncMock()

        await birthdays_list_handler(message, session, state)

        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert len(keyboard.inline_keyboard) == 6  # 5 карточек + навигация
        nav = keyboard.inline_keyboard[5]
        assert [button.text for button in nav] == ["1 / 2", "Стр. 2 ➡️"]

        callback = make_callback("bday_page:2")
        await birthdays_page_handler(callback, session, state)

        rows = callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        assert len(rows) == 2
        nav = rows[-1]
        assert [button.text for button in nav] == ["⬅️ Стр. 1", "2 / 2"]
        counter = nav[1]
        assert counter.callback_data == "noop"


async def test_birthday_card_age_format() -> None:
    import re

    async for session in make_session():
        await seed_person(session)
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert re.search(r"Исполнится: \d+ (год|года|лет)", text) is not None
        assert re.search(r"\(через \d+ (день|дня|дней)\)", text) is not None


async def test_birthday_today_card() -> None:
    from datetime import datetime
    from datetime import timezone as tz_utc

    async for session in make_session():
        today = datetime.now(tz_utc.utc).date()
        await PersonRepository(session).create(
            123,
            fullname="Мама",
            birth_day=today.day,
            birth_month=today.month,
            birth_year=today.year - 42,
        )
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert "🎉" in text
        assert "(СЕГОДНЯ!)" in text
        assert "Исполнилось: 42 года" in text


async def test_birthdays_sorted_by_upcoming() -> None:
    from datetime import datetime, timedelta
    from datetime import timezone as tz_utc

    async for session in make_session():
        today = datetime.now(tz_utc.utc).date()
        far = today + timedelta(days=200)
        near = today + timedelta(days=10)
        await PersonRepository(session).create(
            123, fullname="Далёкий", birth_day=far.day, birth_month=far.month
        )
        await PersonRepository(session).create(
            123, fullname="Близкий", birth_day=near.day, birth_month=near.month
        )
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert text.index("Близкий") < text.index("Далёкий")


async def test_birthday_card_without_year_has_no_age() -> None:
    async for session in make_session():
        await PersonRepository(session).create(123, fullname="Анна", birth_day=1, birth_month=3)
        message = make_message("/birthdays_list")

        await birthdays_list_handler(message, session, AsyncMock())

        text = message.answer.await_args.args[0]
        assert "1 марта" in text
        assert "через" in text
        assert "Исполн" not in text


async def test_edit_menu_shows_current_data() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        state = make_state()
        callback = make_callback(f"edit_bday:{person_id}")
        await birthday_edit_button_handler(callback, session, state)

        text = callback.message.edit_text.await_args.args[0]
        assert "Редактирование:" in text
        assert "Иван" in text
        assert "12 мая 2000" in text
        keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        assert labels == ["👤 Имя", "📅 Дату", "🎁 Заметку", "◀️ Назад к списку"]


async def test_edit_flow_changes_name() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        state = make_state({"bday_id": person_id})
        callback = make_callback("field_bday:name")
        await birthday_edit_field_handler(callback, session, state)
        state.set_state.assert_awaited_once_with(EditBirthdaySG.waiting_for_new_name)
        assert "новое имя" in callback.message.edit_text.await_args.args[0]

        state = make_state({"bday_id": person_id})
        message = make_message("Пётр")
        await birthday_new_name_handler(message, session, state)
        state.clear.assert_awaited_once()

        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.fullname == "Пётр"
        text = message.answer.await_args.args[0]
        assert "обновлён" in text
        keyboard = message.answer.await_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "📋 Назад к списку"


async def test_edit_flow_changes_date() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        state = make_state({"bday_id": person_id})
        callback = make_callback("field_bday:date")
        await birthday_edit_field_handler(callback, session, state)
        state.set_state.assert_awaited_once_with(EditBirthdaySG.waiting_for_new_date)

        state = make_state({"bday_id": person_id})
        await birthday_new_date_handler(make_message("01.02.2001"), session, state)
        state.clear.assert_awaited_once()

        person = await PersonRepository(session).get(person_id)
        assert person is not None
        assert (person.birth_day, person.birth_month, person.birth_year) == (1, 2, 2001)


async def test_edit_flow_rejects_bad_date() -> None:
    async for session in make_session():
        person_id = await seed_person(session)
        state = make_state({"bday_id": person_id, "edit_prompt_id": 44})
        message = make_message("30.02")

        await birthday_new_date_handler(message, session, state)

        state.clear.assert_not_awaited()
        message.delete.assert_awaited_once()
        edited = message.bot.edit_message_text.await_args
        assert edited.kwargs["message_id"] == 44
        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.birth_day == 12


async def test_edit_flow_changes_note_and_clears_it() -> None:
    async for session in make_session():
        person_id = await seed_person(session)

        state = make_state({"bday_id": person_id})
        callback = make_callback("field_bday:note")
        await birthday_edit_field_handler(callback, session, state)
        state.set_state.assert_awaited_once_with(EditBirthdaySG.waiting_for_new_note)
        keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "🗑 Очистить заметку"

        state = make_state({"bday_id": person_id})
        await birthday_new_note_handler(make_message("Дарить книги"), session, state)
        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.notes == "Дарить книги"

        state = make_state({"bday_id": person_id})
        callback = make_callback("clear_note")
        await birthday_clear_note_handler(callback, session, state)
        state.clear.assert_awaited_once()
        person = await PersonRepository(session).get(person_id)
        assert person is not None and person.notes is None


async def test_edit_cancel_returns_to_list() -> None:
    async for session in make_session():
        await seed_person(session)
        state = make_state({"bday_id": 1})
        callback = make_callback(CANCEL_EDIT)

        await birthday_edit_cancel_handler(callback, session, state)

        state.clear.assert_awaited_once()
        assert "Список дней рождения" in callback.message.edit_text.await_args.args[0]


async def test_edit_button_rejects_foreign_person() -> None:
    async for session in make_session():
        person_id = await seed_person(session, tg_id=999)
        state = make_state()

        callback = make_callback(f"edit_bday:{person_id}")
        await birthday_edit_button_handler(callback, session, state)

        state.set_state.assert_not_awaited()
        state.update_data.assert_not_awaited()


async def test_delete_confirm_and_remove() -> None:
    async for session in make_session():
        person_id = await seed_person(session)
        state = make_state({"bday_page": 1})

        callback = make_callback(f"del_bday:{person_id}")
        await birthday_delete_button_handler(callback, session)

        text = callback.message.edit_text.await_args.args[0]
        assert "Вы уверены" in text
        assert "Иван" in text
        keyboard = callback.message.edit_text.await_args.kwargs["reply_markup"]
        assert keyboard.inline_keyboard[0][0].text == "✅ Да, удалить"
        assert keyboard.inline_keyboard[0][1].text == "❌ Отмена"

        callback = make_callback(f"confirm_del_bday:{person_id}")
        await birthday_delete_yes_handler(callback, session, state)

        assert await PersonRepository(session).get(person_id) is None
        assert "успешно удалена" in callback.answer.await_args.args[0].lower()
        assert "пока пуста" in callback.message.edit_text.await_args.args[0]


async def test_delete_cancel_returns_to_list() -> None:
    async for session in make_session():
        person_id = await seed_person(session)
        state = make_state({"bday_page": 1})
        callback = make_callback("cancel_del_bday")

        await birthday_delete_no_handler(callback, session, state)

        assert await PersonRepository(session).get(person_id) is not None
        assert "Список дней рождения" in callback.message.edit_text.await_args.args[0]


async def test_delete_last_on_page_returns_to_previous() -> None:
    async for session in make_session():
        ids = []
        for i in range(6):
            person = await PersonRepository(session).create(
                123, fullname=f"Друг{i}", birth_day=1, birth_month=1
            )
            ids.append(person.id)
        state = make_state({"bday_page": 2})

        callback = make_callback(f"confirm_del_bday:{ids[5]}")
        await birthday_delete_yes_handler(callback, session, state)

        text = callback.message.edit_text.await_args.args[0]
        assert "Друг5" not in text
        rows = callback.message.edit_text.await_args.kwargs["reply_markup"].inline_keyboard
        assert len(rows) == 5


async def test_delete_rejects_foreign_person() -> None:
    async for session in make_session():
        person_id = await seed_person(session, tg_id=999)

        callback = make_callback(f"del_bday:{person_id}")
        await birthday_delete_button_handler(callback, session)

        callback.answer.assert_awaited_once()
        assert await PersonRepository(session).get(person_id) is not None


def test_format_birthday_without_year() -> None:
    person = MagicMock()
    person.fullname = "Анна"
    person.birth_day = 1
    person.birth_month = 3
    person.birth_year = None

    assert format_birthday(person) == "Анна — 01.03"
