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
from src.handlers.birthdays import (
    add_birthday_handler,
    birthday_date_handler,
    birthday_name_handler,
    parse_birthday,
)
from src.handlers.birthdays import router as birthdays_router
from src.handlers.states import BirthdayStates


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
    message.text = text
    message.from_user.id = 123
    message.from_user.username = "owner"
    return message


def make_state(data: dict[str, str] | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


async def test_add_birthday_full_flow() -> None:
    async for session in make_session():
        await add_birthday_handler(make_message("/add_birthday"), session, AsyncMock())
        state = make_state()

        await birthday_name_handler(make_message("Иван"), state)
        state.set_state.assert_awaited_once_with(BirthdayStates.waiting_for_date)

        state = make_state({"fullname": "Иван"})
        await birthday_date_handler(make_message("12.05.2000"), session, state)
        state.clear.assert_awaited_once()

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert (persons[0].fullname, persons[0].birth_day, persons[0].birth_month) == (
            "Иван",
            12,
            5,
        )
        assert persons[0].birth_year == 2000


async def test_birthday_date_without_year() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Анна"})

        await birthday_date_handler(make_message("01.03"), session, state)

        persons = await PersonRepository(session).list_by_owner(123)
        assert len(persons) == 1
        assert persons[0].birth_year is None
        state.clear.assert_awaited_once()


async def test_birthday_date_invalid_stays_in_state() -> None:
    async for session in make_session():
        state = make_state({"fullname": "Иван"})

        await birthday_date_handler(make_message("30.02"), session, state)

        assert await PersonRepository(session).list_by_owner(123) == []
        state.clear.assert_not_awaited()


async def test_birthday_name_empty_stays_in_state() -> None:
    state = AsyncMock()

    await birthday_name_handler(make_message("   "), state)

    state.set_state.assert_not_awaited()


def test_parse_birthday() -> None:
    assert parse_birthday("12.05.2000") == (12, 5, 2000)
    assert parse_birthday("1.3") == (1, 3, None)
    assert parse_birthday("29.02") == (29, 2, None)
    assert parse_birthday("29.02.2023") is None
    assert parse_birthday("32.01") is None
    assert parse_birthday("12.13") is None
    assert parse_birthday("завтра") is None


def test_birthdays_router_is_included() -> None:
    assert birthdays_router in router.sub_routers
