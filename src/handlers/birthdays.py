"""Дни рождения: пошаговое добавление (AddBirthdaySG), список, редактирование."""

import re
from contextlib import suppress
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import PersonRepository, UserRepository
from src.database.models import Person
from src.handlers.birthday_saver import BirthdayDraft, DbBirthdaySaver
from src.handlers.pagination import (
    build_pagination_keyboard,
    days_until,
    page_slice,
    paginate,
    plural,
    turning_age,
)
from src.handlers.prompt import cleanup_step, warn_invalid_input
from src.handlers.states import AddBirthdaySG, EditBirthdayStates

router = Router(name="birthdays")

_DATE_RE = re.compile(r"^\s*(\d{1,2})\s*[.\-/\s]\s*(\d{1,2})(?:\s*[.\-/\s]\s*(\d{4}))?\s*$")

MONTHS_GENITIVE: tuple[str, ...] = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)

ADD_CANCEL = "add_bday:cancel"
ADD_SKIP_NOTE = "add_bday:skip_note"
ADD_AGAIN = "add_bday:again"
ADD_LIST = "add_bday:list"

STEP1_TEXT = (
    "👤 **Шаг 1 из 3: Имя именинника**\n"
    "\n"
    "Напишите имя и фамилию человека (например: *Мама*, *Алексей*, *Катя HR*):"
)

STEP3_TEXT = (
    "📝 **Шаг 3 из 3: Заметка или идеи подарка**\n"
    "\n"
    "Напишите заметку или идею подарка (например: *Любит книги про историю*):\n"
    "\n"
    "Если заметка не нужна, нажмите кнопку ниже:"
)

DATE_PROMPT_KEY = "date_prompt_id"
NAME_PROMPT_KEY = "name_prompt_id"
NOTE_PROMPT_KEY = "note_prompt_id"


CANCELLED_TEXT = "❌ Добавление отменено."


def step2_text(fullname: str) -> str:
    return (
        "📅 **Шаг 2 из 3: Дата рождения**\n"
        "\n"
        f"Напишите дату рождения для **{fullname}** в формате **ДД.ММ** или **ДД.ММ.ГГГГ** "
        "(например: `12.09` или `12.09.1995`):\n"
        "\n"
        "*Указание года необязательно.*"
    )


def build_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=ADD_CANCEL)]]
    )


def build_note_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➡️ Без заметки", callback_data=ADD_SKIP_NOTE)],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=ADD_CANCEL)],
        ]
    )


def build_finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить еще", callback_data=ADD_AGAIN)],
            [InlineKeyboardButton(text="📋 Мой список ДР", callback_data=ADD_LIST)],
        ]
    )


def build_restart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Начать заново", callback_data=ADD_AGAIN)]]
    )


def parse_birthday_date(text: str) -> tuple[int, int, int | None] | None:
    """Парсит ДД.ММ[.ГГГГ] с разделителями . - / пробел. 29.02 без года — ок."""
    match = _DATE_RE.match(text)
    if match is None:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    year = int(match.group(3)) if match.group(3) else None
    try:
        datetime(year if year is not None else 2000, month, day)
    except ValueError:
        return None
    return day, month, year


def format_birthday_long(day: int, month: int, year: int | None) -> str:
    text = f"{day} {MONTHS_GENITIVE[month - 1]}"
    if year is not None:
        text += f" {year}"
    return text


def build_finish_text(draft: BirthdayDraft) -> str:
    note = draft.note if draft.note else "нет"
    date = format_birthday_long(draft.day, draft.month, draft.year)
    return (
        "🎉 **День рождения успешно сохранен!**\n"
        "\n"
        f"👤 **Именинник:** {draft.fullname}\n"
        f"📅 **Дата:** {date}\n"
        f"📝 **Заметка:** {note}"
    )


async def finish_add_birthday(
    db: AsyncSession, state: FSMContext, tg_id: int, note: str | None, answer_to: Message
) -> None:
    data = await state.get_data()
    try:
        draft = BirthdayDraft(
            fullname=data["fullname"],
            day=int(data["day"]),
            month=int(data["month"]),
            year=data.get("year"),
            note=note,
        )
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await answer_to.answer("Что-то пошло не так. Начни заново: /add_birthday.")
        return
    await DbBirthdaySaver(db).save_birthday(tg_id, draft)
    await state.clear()
    await answer_to.answer(
        build_finish_text(draft),
        reply_markup=build_finish_keyboard(),
        parse_mode="Markdown",
    )


@router.message(Command("add_birthday"))
async def add_birthday_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await UserRepository(db).get_or_create(
        message.from_user.id, username=message.from_user.username
    )
    await state.set_state(AddBirthdaySG.waiting_for_name)
    sent = await message.answer(
        STEP1_TEXT, reply_markup=build_cancel_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(name_prompt_id=sent.message_id)


@router.message(AddBirthdaySG.waiting_for_name, F.text)
async def birthday_name_handler(message: Message, state: FSMContext) -> None:
    fullname = (message.text or "").strip()
    if not fullname:
        await message.answer("Имя не может быть пустым. Напиши имя именинника.")
        return
    if len(fullname) > 255:
        await message.answer("Слишком длинное имя (максимум 255 символов). Напиши покороче.")
        return
    await state.update_data(fullname=fullname)
    await state.set_state(AddBirthdaySG.waiting_for_date)
    await cleanup_step(message, state, NAME_PROMPT_KEY)
    sent = await message.answer(
        step2_text(fullname), reply_markup=build_cancel_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(date_prompt_id=sent.message_id)


@router.message(AddBirthdaySG.waiting_for_date, F.text)
async def birthday_date_handler(message: Message, state: FSMContext) -> None:
    parsed = parse_birthday_date(message.text or "")
    if parsed is None:
        data = await state.get_data()
        fullname = str(data.get("fullname", "именинника"))
        await warn_invalid_input(
            message,
            state,
            DATE_PROMPT_KEY,
            step2_text(fullname),
            build_cancel_keyboard(),
        )
        return
    day, month, year = parsed
    await state.update_data(day=day, month=month, year=year)
    await state.set_state(AddBirthdaySG.waiting_for_note)
    await cleanup_step(message, state, DATE_PROMPT_KEY)
    sent = await message.answer(
        STEP3_TEXT, reply_markup=build_note_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(note_prompt_id=sent.message_id)


@router.message(AddBirthdaySG.waiting_for_note, F.text)
async def birthday_note_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    note = (message.text or "").strip()
    await cleanup_step(message, state, NOTE_PROMPT_KEY)
    await finish_add_birthday(db, state, message.from_user.id, note, message)


@router.callback_query(F.data == ADD_SKIP_NOTE)
async def birthday_skip_note_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None:
        return
    data = await state.get_data()
    if "fullname" not in data or "day" not in data or "month" not in data:
        await callback.answer("Начни добавление заново: /add_birthday.", show_alert=True)
        return
    await callback.answer()
    target = callback.message if isinstance(callback.message, Message) else None
    if target is None:
        return
    with suppress(TelegramBadRequest):
        await target.delete()
    await finish_add_birthday(db, state, callback.from_user.id, None, target)


@router.callback_query(F.data == ADD_CANCEL)
async def birthday_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CANCELLED_TEXT, reply_markup=build_restart_keyboard())


@router.callback_query(F.data == ADD_AGAIN)
async def birthday_again_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddBirthdaySG.waiting_for_name)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            STEP1_TEXT, reply_markup=build_cancel_keyboard(), parse_mode="Markdown"
        )
        await state.update_data(name_prompt_id=callback.message.message_id)


@router.callback_query(F.data == ADD_LIST)
async def birthday_list_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await edit_birthdays_page(callback.message, db, callback.from_user.id, 1, state)


EMPTY_BDAY_TEXT = "🎈 Ваша база дней рождения пока пуста."


BDAY_PAGE_PREFIX = "bday_page"
EDIT_BDAY_PREFIX = "edit_bday:"
DEL_BDAY_PREFIX = "del_bday:"
CONFIRM_DEL_BDAY_PREFIX = "confirm_del_bday:"
CANCEL_DEL_BDAY = "cancel_del_bday"
FIELD_PREFIX = "bedit:"
FIELD_FULLNAME = "fullname"
FIELD_DATE = "date"
FIELD_USERNAME = "username"
FIELD_NOTES = "notes"
BDAY_PAGE_KEY = "bday_page"

FIELD_LABELS: dict[str, str] = {
    FIELD_FULLNAME: "Имя",
    FIELD_DATE: "Дата",
    FIELD_USERNAME: "Username",
    FIELD_NOTES: "Заметка",
}


def format_birthday(person: Person) -> str:
    date = f"{person.birth_day:02d}.{person.birth_month:02d}"
    if person.birth_year:
        date += f".{person.birth_year}"
    return f"{person.fullname} — {date}"


def card_button_name(fullname: str) -> str:
    return fullname.split()[0] if fullname.split() else fullname


def build_birthdays_page_keyboard(
    persons: list[Person], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"✏️ {card_button_name(person.fullname)}",
                callback_data=f"{EDIT_BDAY_PREFIX}{person.id}",
            ),
            InlineKeyboardButton(
                text=f"🗑 {card_button_name(person.fullname)}",
                callback_data=f"{DEL_BDAY_PREFIX}{person.id}",
            ),
        ]
        for person in persons[page_slice(page)]
    ]
    nav = build_pagination_keyboard(BDAY_PAGE_PREFIX, page, total_pages, numbered_nav=True)
    if nav is not None:
        rows.extend(nav.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "noop")
async def noop_handler(callback: CallbackQuery) -> None:
    await callback.answer()


def build_fields_keyboard(person_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{FIELD_PREFIX}{person_id}:{field}")]
        for field, label in FIELD_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_delete_confirm_keyboard(person_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"{CONFIRM_DEL_BDAY_PREFIX}{person_id}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data=CANCEL_DEL_BDAY),
            ]
        ]
    )


def user_today(tz_name: str | None) -> date:
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def build_birthday_card(person: Person, index: int, today: date) -> str:
    date_text = f"{person.birth_day} {MONTHS_GENITIVE[person.birth_month - 1]}"
    until = days_until(person.birth_day, person.birth_month, today)
    age = turning_age(person.birth_day, person.birth_month, person.birth_year, today)
    if until == 0:
        head = f"🎉 **{index}. {person.fullname}** — **{date_text}** *(СЕГОДНЯ!)*"
        age_verb = "Исполнилось"
    else:
        head = (
            f"🎈 **{index}. {person.fullname}** — **{date_text}** "
            f"*(через {until} {plural(until, 'день', 'дня', 'дней')})*"
        )
        age_verb = "Исполнится"
    lines = [head]
    if age is not None:
        lines.append(f"🎂 {age_verb}: {age} {plural(age, 'год', 'года', 'лет')}")
    if person.notes:
        lines.append(f"📝 *«{person.notes}»*")
    return "\n".join(lines)


def sort_by_upcoming(persons: list[Person], today: date) -> list[Person]:
    return sorted(
        persons, key=lambda person: days_until(person.birth_day, person.birth_month, today)
    )


def build_birthdays_page_text(persons: list[Person], page: int, today: date) -> str:
    header = f"📋 **Список дней рождения (всего: {len(persons)})**"
    offset = (page - 1) * 5
    cards = [
        build_birthday_card(person, offset + i + 1, today)
        for i, person in enumerate(persons[page_slice(page)])
    ]
    return header + "\n\n" + "\n───\n".join(cards) + "\n\n👇 *Кнопки управления:*"


async def get_bday_page(state: FSMContext) -> int:
    data = await state.get_data()
    try:
        return max(1, int(data.get(BDAY_PAGE_KEY, 1)))
    except (TypeError, ValueError):
        return 1


async def answer_birthdays_page(
    message: Message, db: AsyncSession, tg_id: int, page: int, state: FSMContext
) -> None:
    user = await UserRepository(db).get_by_tg_id(tg_id)
    persons = await PersonRepository(db).list_by_owner(tg_id)
    if not persons:
        await message.answer(EMPTY_BDAY_TEXT)
        return
    page, total_pages = paginate(len(persons), page)
    await state.update_data(bday_page=page)
    today = user_today(user.time_zone if user else None)
    persons = sort_by_upcoming(persons, today)
    await message.answer(
        build_birthdays_page_text(persons, page, today),
        reply_markup=build_birthdays_page_keyboard(persons, page, total_pages),
        parse_mode="Markdown",
    )


async def edit_birthdays_page(
    message: Message, db: AsyncSession, tg_id: int, page: int, state: FSMContext
) -> None:
    user = await UserRepository(db).get_by_tg_id(tg_id)
    persons = await PersonRepository(db).list_by_owner(tg_id)
    if not persons:
        await message.edit_text(EMPTY_BDAY_TEXT)
        return
    page, total_pages = paginate(len(persons), page)
    await state.update_data(bday_page=page)
    today = user_today(user.time_zone if user else None)
    persons = sort_by_upcoming(persons, today)
    await message.edit_text(
        build_birthdays_page_text(persons, page, today),
        reply_markup=build_birthdays_page_keyboard(persons, page, total_pages),
        parse_mode="Markdown",
    )


async def get_owned_person(db: AsyncSession, tg_id: int, person_id: int) -> Person | None:
    person = await PersonRepository(db).get(person_id)
    if person is None or person.tg_id != tg_id:
        return None
    return person


@router.message(Command("birthdays_list"))
async def birthdays_list_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await answer_birthdays_page(message, db, message.from_user.id, 1, state)


@router.callback_query(F.data.startswith(BDAY_PAGE_PREFIX + ":"))
async def birthdays_page_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        return
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await callback.answer()
    await edit_birthdays_page(callback.message, db, callback.from_user.id, page, state)


@router.message(Command("edit_birthday"))
async def edit_birthday_hint_handler(message: Message) -> None:
    await message.answer(
        "Чтобы изменить день рождения, открой /birthdays_list и нажми ✏️ под нужной записью."
    )


@router.callback_query(F.data.startswith(EDIT_BDAY_PREFIX))
async def birthday_edit_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(EDIT_BDAY_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.set_state(EditBirthdayStates.choosing_field)
    await state.update_data(person_id=person_id)
    await callback.answer()
    await callback.message.edit_text(
        f"{format_birthday(person)}\n\nЧто изменить?",
        reply_markup=build_fields_keyboard(person_id),
    )


# Без фильтра состояния: person_id уже зашит в callback_data,
# состояние выставляется заново внутри хендлера.
@router.callback_query(F.data.startswith(FIELD_PREFIX))
async def birthday_field_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        _, person_id_text, field = callback.data.removeprefix(FIELD_PREFIX).split(":")
        person_id = int(person_id_text)
    except ValueError:
        await callback.answer("Некорректное поле.", show_alert=True)
        return
    if field not in FIELD_LABELS:
        await callback.answer("Некорректное поле.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.set_state(EditBirthdayStates.waiting_for_value)
    await state.update_data(person_id=person_id, field=field)
    await callback.answer()
    prompts = {
        FIELD_FULLNAME: "Пришли новое имя.",
        FIELD_DATE: "Пришли новую дату в формате ДД.ММ или ДД.ММ.ГГГГ.",
        FIELD_USERNAME: "Пришли новый username (без @) или «-», чтобы убрать.",
        FIELD_NOTES: "Пришли новую заметку или «-», чтобы убрать.",
    }
    await callback.message.edit_text(f"{format_birthday(person)}\n\n{prompts[field]}")


@router.message(EditBirthdayStates.waiting_for_value, F.text)
async def birthday_value_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    person = await get_owned_person(db, message.from_user.id, int(data.get("person_id", -1)))
    if person is None:
        await state.clear()
        await message.answer("Запись не найдена. Открой /birthdays_list и попробуй снова.")
        return
    field = data.get("field")
    value = (message.text or "").strip()
    updates: dict[str, object]
    if field == FIELD_FULLNAME:
        if not value or len(value) > 255:
            await message.answer("Имя должно быть от 1 до 255 символов. Попробуй ещё раз.")
            return
        updates = {"fullname": value}
    elif field == FIELD_DATE:
        parsed = parse_birthday_date(value)
        if parsed is None:
            await message.answer("Не понял дату. Формат: ДД.ММ или ДД.ММ.ГГГГ.")
            return
        day, month, year = parsed
        updates = {"birth_day": day, "birth_month": month, "birth_year": year}
    elif field == FIELD_USERNAME:
        updates = {"username": None if value == "-" else value.lstrip("@")}
    elif field == FIELD_NOTES:
        updates = {"notes": None if value == "-" else value}
    else:
        await state.clear()
        await message.answer("Неизвестное поле. Открой /birthdays_list и попробуй снова.")
        return
    updated = await PersonRepository(db).update(person.id, **updates)
    await state.clear()
    if updated is None:
        await message.answer("Не удалось сохранить. Попробуй снова: /birthdays_list.")
        return
    await message.answer(f"Готово! {format_birthday(updated)}")


@router.callback_query(F.data.startswith(DEL_BDAY_PREFIX))
async def birthday_delete_button_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(DEL_BDAY_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await callback.answer()
    date_text = format_birthday_long(person.birth_day, person.birth_month, person.birth_year)
    await callback.message.edit_text(
        "⚠️ **Вы уверены, что хотите удалить день рождения?**\n"
        "\n"
        f"👤 **{person.fullname}** ({date_text})\n"
        "\n"
        "*Это действие нельзя отменить.*",
        reply_markup=build_delete_confirm_keyboard(person_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CONFIRM_DEL_BDAY_PREFIX))
async def birthday_delete_yes_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(CONFIRM_DEL_BDAY_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await PersonRepository(db).delete(person_id)
    await callback.answer("Запись успешно удалена")
    page = await get_bday_page(state)
    await edit_birthdays_page(callback.message, db, callback.from_user.id, page, state)


@router.callback_query(F.data == CANCEL_DEL_BDAY)
async def birthday_delete_no_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        page = await get_bday_page(state)
        await edit_birthdays_page(callback.message, db, callback.from_user.id, page, state)
