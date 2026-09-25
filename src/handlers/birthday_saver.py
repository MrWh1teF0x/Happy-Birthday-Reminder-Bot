"""Сервис сохранения дня рождения.

Логика шагов FSM работает с `BirthdaySaver` через протокол —
ей не важны названия колонок и таблиц в БД.
"""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import PersonRepository


@dataclass
class BirthdayDraft:
    fullname: str
    day: int
    month: int
    year: int | None
    note: str | None


class BirthdaySaver(Protocol):
    async def save_birthday(self, owner_tg_id: int, draft: BirthdayDraft) -> None:
        """Сохранить черновик дня рождения за владельцем. Реализация — любая."""
        ...


class DbBirthdaySaver:
    """Реализация поверх репозитория persons."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_birthday(self, owner_tg_id: int, draft: BirthdayDraft) -> None:
        await PersonRepository(self._db).create(
            owner_tg_id,
            fullname=draft.fullname,
            birth_day=draft.day,
            birth_month=draft.month,
            birth_year=draft.year,
            notes=draft.note,
        )
