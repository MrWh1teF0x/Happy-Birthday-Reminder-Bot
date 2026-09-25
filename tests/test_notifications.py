from collections.abc import AsyncIterator
from datetime import date, datetime, time, timezone
from typing import Any
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from src.database import (
    PersonRepository,
    SentNotificationRepository,
    UserRepository,
    UserSettingRepository,
)
from src.database.models import Base
from src.notifications import check_notifications, collect_due_notifications

NOW = datetime(2026, 9, 5, 10, 0, tzinfo=timezone.utc)


async def make_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine: AsyncEngine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    await engine.dispose()


async def seed(
    session: AsyncSession,
    *,
    tg_id: int = 123,
    tz: str = "UTC",
    day: int = 12,
    month: int = 9,
    year: int | None = 1995,
    note: str | None = None,
    days_before: int = 7,
    at: time = time(9, 0),
    enabled: bool = True,
) -> tuple[int, int]:
    await UserRepository(session).get_or_create(tg_id, time_zone=tz)
    await UserRepository(session).set_time_zone(tg_id, tz)
    person = await PersonRepository(session).create(
        tg_id, fullname="Иван", birth_day=day, birth_month=month, birth_year=year, notes=note
    )
    setting = await UserSettingRepository(session).create(
        tg_id, notify_days_before=days_before, notification_time=at, is_enabled=enabled
    )
    return person.id, setting.id


def make_bot() -> Any:
    return AsyncMock()


async def test_sends_due_notification_and_logs() -> None:
    async for maker in make_factory():
        async with maker() as session:
            person_id, setting_id = await seed(session)
            await session.commit()
        bot = make_bot()

        sent = await check_notifications(bot, maker, NOW)

        assert sent == 1
        bot.send_message.assert_awaited_once()
        text = bot.send_message.await_args.args[1]
        assert "Иван" in text
        assert "31 год" in text
        async with maker() as session:
            repo = SentNotificationRepository(session)
            assert await repo.was_sent(123, person_id, setting_id, date(2026, 9, 5))


async def test_no_double_send_same_day() -> None:
    async for maker in make_factory():
        async with maker() as session:
            await seed(session)
            await session.commit()
        bot = make_bot()

        assert await check_notifications(bot, maker, NOW) == 1
        assert await check_notifications(bot, maker, NOW) == 0

        assert bot.send_message.await_count == 1


async def test_skips_future_time_disabled_and_mismatch() -> None:
    async for maker in make_factory():
        async with maker() as session:
            await seed(session, tg_id=1, at=time(11, 0))  # время ещё не наступило
            await seed(session, tg_id=2, enabled=False)  # выключено
            await seed(session, tg_id=3, day=1, month=1)  # дата не совпала
            await session.commit()

        assert await check_notifications(make_bot(), maker, NOW) == 0


async def test_today_birthday_text() -> None:
    async for maker in make_factory():
        async with maker() as session:
            await seed(session, day=5, month=9, days_before=0)
            await session.commit()
        bot = make_bot()

        assert await check_notifications(bot, maker, NOW) == 1

        assert "СЕГОДНЯ" in bot.send_message.await_args.args[1]


async def test_user_timezone_applies() -> None:
    moscow_morning = datetime(2026, 9, 5, 6, 0, tzinfo=timezone.utc)  # 09:00 МСК
    async for maker in make_factory():
        async with maker() as session:
            await seed(session, tz="Europe/Moscow", day=12, month=9)
            await session.commit()

        assert await check_notifications(make_bot(), maker, moscow_morning) == 1


async def test_blocked_bot_is_logged_without_raise() -> None:
    async for maker in make_factory():
        async with maker() as session:
            await seed(session)
            await session.commit()
        bot = make_bot()
        bot.send_message = AsyncMock(
            side_effect=TelegramForbiddenError(
                method=SendMessage(chat_id=123, text="x"), message="Forbidden"
            )
        )

        assert await check_notifications(bot, maker, NOW) == 1
        assert await check_notifications(bot, maker, NOW) == 0


async def test_collect_returns_due_items() -> None:
    async for maker in make_factory():
        async with maker() as session:
            await seed(session, note="Книги")
            await session.commit()

        due = await collect_due_notifications(maker, NOW)

        assert len(due) == 1
        assert due[0].fullname == "Иван"
        assert due[0].days_before == 7
        assert due[0].note == "Книги"
