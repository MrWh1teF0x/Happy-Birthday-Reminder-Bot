"""Добавление дня рождения: имя → дата ДД.ММ[.ГГГГ]."""

import re
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import PersonRepository, UserRepository
from src.handlers.states import BirthdayStates

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
