"""Сервис сохранения напоминаний.

Логика шагов FSM работает с `ReminderSaver` через протокол —
защита от дублей и детали хранения инкапсулированы в реализации.
"""

from datetime import time as time_type
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserSettingRepository
from src.database.models import UserSetting


class ReminderSaver(Protocol):
    async def save_reminder(self, tg_id: int, days_before: int, moment: time_type) -> UserSetting:
        """Сохранить напоминание. Реализация — любая."""
        ...


class DbReminderSaver:
    """Реализация поверх user_settings: дубль по интервалу не создаётся —
    у существующего интервала обновляется время отправки."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save_reminder(self, tg_id: int, days_before: int, moment: time_type) -> UserSetting:
        repo = UserSettingRepository(self._db)
        existing = await repo.get_by_days(tg_id, days_before)
        if existing is not None:
            updated = await repo.update(existing.id, notification_time=moment)
            assert updated is not None
            return updated
        return await repo.create(tg_id, notify_days_before=days_before, notification_time=moment)
