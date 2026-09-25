"""Карточные списки с пагинацией: нарезка страниц, клавиатуры, склонения, даты."""

import calendar
from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

PAGE_SIZE = 5


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def paginate(total: int, page: int, per_page: int = PAGE_SIZE) -> tuple[int, int]:
    """Возвращает (текущая страница с клампом, всего страниц)."""
    total_pages = max(1, (total + per_page - 1) // per_page)
    return min(max(1, page), total_pages), total_pages


def page_slice(page: int, per_page: int = PAGE_SIZE) -> slice:
    start = (page - 1) * per_page
    return slice(start, start + per_page)


def build_pagination_keyboard(
    prefix: str, page: int, total_pages: int
) -> InlineKeyboardMarkup | None:
    """Блок навигации. Одна страница — кнопок нет (None)."""
    if total_pages <= 1:
        return None
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}:{page - 1}"))
    row.append(
        InlineKeyboardButton(text=f"{page} / {total_pages}", callback_data=f"{prefix}:{page}")
    )
    if page < total_pages:
        row.append(InlineKeyboardButton(text="Вперед ➡️", callback_data=f"{prefix}:{page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def keycap_number(n: int) -> str:
    if 1 <= n <= 9:
        return f"{n}\ufe0f\u20e3"
    return f"{n}."


def next_occurrence(day: int, month: int, today: date) -> date:
    """Ближайшая дата ДР (29.02 в невисокосный год — 28.02)."""
    year = today.year
    while True:
        last_day = calendar.monthrange(year, month)[1]
        candidate = date(year, month, min(day, last_day))
        if candidate >= today:
            return candidate
        year += 1


def days_until(day: int, month: int, today: date) -> int:
    return (next_occurrence(day, month, today) - today).days


def turning_age(day: int, month: int, year: int | None, today: date) -> int | None:
    if year is None:
        return None
    return next_occurrence(day, month, today).year - year
