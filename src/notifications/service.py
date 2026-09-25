"""Фоновая служба напоминаний: сбор due-уведомлений и отправка через бота."""

import logging
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database import (
    PersonRepository,
    SentNotificationRepository,
    UserRepository,
    UserSettingRepository,
)
from src.handlers.birthday_notify import (
    build_birthday_notification,
    build_notification_keyboard,
)

logger = logging.getLogger(__name__)

CHECK_INTERVAL_MINUTES = 15


@dataclass
class DueNotification:
    tg_id: int
    person_id: int
    setting_id: int
    fullname: str
    day: int
    month: int
    year: int | None
    note: str | None
    days_before: int
    today: date_type


def user_zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or "UTC")
    except Exception:
        return ZoneInfo("UTC")


async def collect_due_notifications(
    session_factory: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> list[DueNotification]:
    """Найти все напоминания к отправке: совпадение даты + время наступило + не слали сегодня."""
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    due: list[DueNotification] = []
    async with session_factory() as session:
        users = await UserRepository(session).list_all()
        for user in users:
            local_now = now_utc.astimezone(user_zone(user.time_zone))
            today = local_now.date()
            settings = await UserSettingRepository(session).list_by_user(user.tg_id)
            for setting in settings:
                if not setting.is_enabled:
                    continue
                if local_now.time() < setting.notification_time:
                    continue
                target = today + timedelta(days=setting.notify_days_before)
                persons = await PersonRepository(session).list_by_birthdate(
                    user.tg_id, target.day, target.month
                )
                sent = SentNotificationRepository(session)
                for person in persons:
                    if await sent.was_sent(user.tg_id, person.id, setting.id, today):
                        continue
                    due.append(
                        DueNotification(
                            tg_id=user.tg_id,
                            person_id=person.id,
                            setting_id=setting.id,
                            fullname=person.fullname,
                            day=person.birth_day,
                            month=person.birth_month,
                            year=person.birth_year,
                            note=person.notes,
                            days_before=setting.notify_days_before,
                            today=today,
                        )
                    )
    return due


async def check_notifications(
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    now: datetime | None = None,
) -> int:
    """Одна проверка планировщика: отправить due и залогировать. Возвращает число отправок."""
    due = await collect_due_notifications(session_factory, now)
    sent_count = 0
    for item in due:
        text = build_birthday_notification(
            fullname=item.fullname,
            day=item.day,
            month=item.month,
            year=item.year,
            note=item.note,
            days_before=item.days_before,
            today=item.today,
        )
        try:
            await bot.send_message(
                item.tg_id,
                text,
                reply_markup=build_notification_keyboard(item.person_id),
                parse_mode="Markdown",
            )
        except TelegramForbiddenError:
            logger.warning("User %s blocked the bot, marking notification as sent", item.tg_id)
        except TelegramAPIError:
            logger.exception("Failed to send notification to %s", item.tg_id)
            continue
        async with session_factory() as session:
            await SentNotificationRepository(session).mark_sent(
                item.tg_id, item.person_id, item.setting_id, item.today
            )
            await session.commit()
        sent_count += 1
    if sent_count:
        logger.info("Sent %d birthday notifications", sent_count)
    return sent_count
