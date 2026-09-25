"""Дни рождения: пошаговое добавление (AddBirthdaySG), список, редактирование."""

import re
from contextlib import suppress
from datetime import datetime

from aiogram import Bot, F, Router
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

DATE_ERROR_TEXT = (
    "⚠️ Некорректный формат даты. Попробуйте еще раз (например: `12.09` или `12.09.1995`)."
)

DATE_PROMPT_KEY = "date_prompt_id"


async def delete_step_message(bot: Bot, chat_id: int, state: FSMContext, key: str) -> None:
    data = await state.get_data()
    prompt_id = data.get(key)
    if isinstance(prompt_id, int):
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, prompt_id)


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


def build_add_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="➕ Добавить", callback_data=ADD_AGAIN)]]
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
        f"🎁 **Заметка:** {note}"
    )


async def finish_add_birthday(
    db: AsyncSession,
    state: FSMContext,
    tg_id: int,
    note: str | None,
    edit_message: Message | None,
    answer_to: Message,
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
    if edit_message is not None:
        await edit_message.edit_text(
            build_finish_text(draft),
            reply_markup=build_finish_keyboard(),
            parse_mode="Markdown",
        )
    else:
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
    await message.answer(STEP1_TEXT, reply_markup=build_cancel_keyboard(), parse_mode="Markdown")


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
    sent = await message.answer(
        step2_text(fullname), reply_markup=build_cancel_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(date_prompt_id=sent.message_id)


@router.message(AddBirthdaySG.waiting_for_date, F.text)
async def birthday_date_handler(message: Message, state: FSMContext) -> None:
    parsed = parse_birthday_date(message.text or "")
    if parsed is None:
        if message.bot is not None:
            await delete_step_message(message.bot, message.chat.id, state, DATE_PROMPT_KEY)
            with suppress(TelegramBadRequest):
                await message.delete()
        error = await message.answer(DATE_ERROR_TEXT, parse_mode="Markdown")
        await state.update_data(date_prompt_id=error.message_id)
        return
    day, month, year = parsed
    await state.update_data(day=day, month=month, year=year)
    await state.set_state(AddBirthdaySG.waiting_for_note)
    await message.answer(STEP3_TEXT, reply_markup=build_note_keyboard(), parse_mode="Markdown")


@router.message(AddBirthdaySG.waiting_for_note, F.text)
async def birthday_note_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await finish_add_birthday(
        db, state, message.from_user.id, (message.text or "").strip(), None, message
    )


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
    await finish_add_birthday(db, state, callback.from_user.id, None, target, target)


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


@router.callback_query(F.data == ADD_LIST)
async def birthday_list_button_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    persons = await PersonRepository(db).list_by_owner(callback.from_user.id)
    if not persons:
        await callback.message.edit_text(EMPTY_LIST_TEXT, reply_markup=build_add_keyboard())
        return
    lines = [f"{i}. {format_birthday(person)}" for i, person in enumerate(persons, 1)]
    await callback.message.edit_text(
        "Сохранённые дни рождения:\n\n" + "\n".join(lines),
        reply_markup=build_birthdays_keyboard(persons),
    )


EMPTY_LIST_TEXT = (
    "✨ Здесь пока ничего нет, но это легко исправить!\n"
    "\n"
    "Добавь день рождения близкого человека, друга или коллеги, "
    "чтобы не забыть поздравить и вовремя подготовить подарок 🎁\n"
    "\n"
    "👉 Нажми сюда: /add_birthday"
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
        await message.answer(EMPTY_LIST_TEXT, reply_markup=build_add_keyboard())
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
        await callback.message.edit_text(EMPTY_LIST_TEXT)
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
            await callback.message.edit_text(EMPTY_LIST_TEXT)
            return
        lines = [f"{i}. {format_birthday(item)}" for i, item in enumerate(persons, 1)]
        await callback.message.edit_text(
            "Сохранённые дни рождения:\n\n" + "\n".join(lines),
            reply_markup=build_birthdays_keyboard(persons),
        )
