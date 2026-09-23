"""Добавление дня рождения: имя → дата ДД.ММ[.ГГГГ]."""

import re
from datetime import datetime

from aiogram import F, Router
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
from src.handlers.states import BirthdayStates, EditBirthdayStates

router = Router(name="birthdays")

_DATE_RE = re.compile(r"^\s*(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s*$")


def parse_birthday(text: str) -> tuple[int, int, int | None] | None:
    """Парсит ДД.ММ[.ГГГГ], проверяет реальность даты. 29.02 без года — ок."""
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


@router.message(Command("add_birthday"))
async def add_birthday_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await UserRepository(db).get_or_create(
        message.from_user.id, username=message.from_user.username
    )
    await state.set_state(BirthdayStates.waiting_for_fullname)
    await message.answer("Как зовут именинника? Пришли имя.")


@router.message(BirthdayStates.waiting_for_fullname, F.text)
async def birthday_name_handler(message: Message, state: FSMContext) -> None:
    fullname = (message.text or "").strip()
    if not fullname:
        await message.answer("Имя не может быть пустым. Пришли имя именинника.")
        return
    if len(fullname) > 255:
        await message.answer("Слишком длинное имя (максимум 255 символов). Пришли покороче.")
        return
    await state.update_data(fullname=fullname)
    await state.set_state(BirthdayStates.waiting_for_date)
    await message.answer(
        f"Записал: {fullname}. Теперь пришли дату рождения в формате ДД.ММ или ДД.ММ.ГГГГ "
        "(например, 12.05 или 12.05.2000)."
    )


@router.message(BirthdayStates.waiting_for_date, F.text)
async def birthday_date_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    parsed = parse_birthday(message.text or "")
    if parsed is None:
        await message.answer(
            "Не понял дату. Нужен формат ДД.ММ или ДД.ММ.ГГГГ — например, 12.05 или 12.05.2000."
        )
        return
    day, month, year = parsed
    data = await state.get_data()
    person = await PersonRepository(db).create(
        message.from_user.id,
        fullname=data.get("fullname", "Без имени"),
        birth_day=day,
        birth_month=month,
        birth_year=year,
    )
    await state.clear()
    date_text = f"{day:02d}.{month:02d}" + (f".{year}" if year else "")
    await message.answer(
        f"Готово! {person.fullname} — {date_text}. Посмотреть всех: /birthdays_list."
    )


EDIT_PREFIX = "birthday:edit:"
DELETE_PREFIX = "birthday:del:"
DELETE_YES_PREFIX = "bdel_yes:"
DELETE_NO_PREFIX = "bdel_no:"
FIELD_PREFIX = "bedit:"
FIELD_FULLNAME = "fullname"
FIELD_DATE = "date"
FIELD_USERNAME = "username"
FIELD_NOTES = "notes"

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


def build_birthdays_keyboard(persons: list[Person]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"✏️ {person.fullname}", callback_data=f"{EDIT_PREFIX}{person.id}"
            ),
            InlineKeyboardButton(text="🗑", callback_data=f"{DELETE_PREFIX}{person.id}"),
        ]
        for person in persons
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
                    text="Да, удалить", callback_data=f"{DELETE_YES_PREFIX}{person_id}"
                ),
                InlineKeyboardButton(text="Нет", callback_data=f"{DELETE_NO_PREFIX}{person_id}"),
            ]
        ]
    )


async def get_owned_person(db: AsyncSession, tg_id: int, person_id: int) -> Person | None:
    person = await PersonRepository(db).get(person_id)
    if person is None or person.tg_id != tg_id:
        return None
    return person


async def render_birthdays(message: Message, db: AsyncSession, tg_id: int) -> None:
    persons = await PersonRepository(db).list_by_owner(tg_id)
    if not persons:
        await message.answer("Пока пусто. Добавь первый день рождения: /add_birthday.")
        return
    lines = [f"{i}. {format_birthday(person)}" for i, person in enumerate(persons, 1)]
    await message.answer(
        "Сохранённые дни рождения:\n\n" + "\n".join(lines),
        reply_markup=build_birthdays_keyboard(persons),
    )


@router.message(Command("birthdays_list"))
async def birthdays_list_handler(message: Message, db: AsyncSession) -> None:
    if message.from_user is None:
        return
    await render_birthdays(message, db, message.from_user.id)


@router.message(Command("edit_birthday"))
async def edit_birthday_hint_handler(message: Message) -> None:
    await message.answer(
        "Чтобы изменить день рождения, открой /birthdays_list и нажми ✏️ под нужной записью."
    )


@router.callback_query(F.data.startswith(EDIT_PREFIX))
async def birthday_edit_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(EDIT_PREFIX))
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
        parsed = parse_birthday(value)
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


@router.callback_query(F.data.startswith(DELETE_PREFIX))
async def birthday_delete_button_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(DELETE_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"Удалить {format_birthday(person)}?",
        reply_markup=build_delete_confirm_keyboard(person_id),
    )


@router.callback_query(F.data.startswith(DELETE_YES_PREFIX))
async def birthday_delete_yes_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        person_id = int(callback.data.removeprefix(DELETE_YES_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    person = await get_owned_person(db, callback.from_user.id, person_id)
    if person is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await PersonRepository(db).delete(person_id)
    await callback.answer("Удалено.")
    persons = await PersonRepository(db).list_by_owner(callback.from_user.id)
    if not persons:
        await callback.message.edit_text("Готово, удалил. Список пуст — добавить: /add_birthday.")
        return
    lines = [f"{i}. {format_birthday(item)}" for i, item in enumerate(persons, 1)]
    await callback.message.edit_text(
        "Готово, удалил.\n\nСохранённые дни рождения:\n\n" + "\n".join(lines),
        reply_markup=build_birthdays_keyboard(persons),
    )


@router.callback_query(F.data.startswith(DELETE_NO_PREFIX))
async def birthday_delete_no_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        persons = await PersonRepository(db).list_by_owner(callback.from_user.id)
        if not persons:
            await callback.message.edit_text("Список пуст — добавить: /add_birthday.")
            return
        lines = [f"{i}. {format_birthday(item)}" for i, item in enumerate(persons, 1)]
        await callback.message.edit_text(
            "Сохранённые дни рождения:\n\n" + "\n".join(lines),
            reply_markup=build_birthdays_keyboard(persons),
        )
