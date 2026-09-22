from collections.abc import AsyncIterator
from datetime import time

from pytest import fixture, raises
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database import (
    PersonRepository,
    UserRepository,
    UserSettingRepository,
)
from src.database.models import Base, Person


@fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as current_session:
        yield current_session
        await current_session.rollback()
    await engine.dispose()


async def test_user_defaults(session: AsyncSession) -> None:
    repo = UserRepository(session)

    user = await repo.get_or_create(123, username="owner")

    assert user.tg_id == 123
    assert user.time_zone == "UTC"
    assert user.created_at is not None


async def test_get_or_create_returns_existing(session: AsyncSession) -> None:
    repo = UserRepository(session)

    first = await repo.get_or_create(123)
    second = await repo.get_or_create(123, username="owner")

    assert first.tg_id == second.tg_id
    assert second.username == "owner"


async def test_person_crud_and_owner_link(session: AsyncSession) -> None:
    users = UserRepository(session)
    persons = PersonRepository(session)
    await users.get_or_create(123)

    person = await persons.create(
        123, fullname="Иван", birth_day=15, birth_month=5, birth_year=1990, notes="Любит книги"
    )

    assert person.id is not None
    assert person.created_at is not None
    assert person.owner.tg_id == 123

    listed = await persons.list_by_owner(123)
    assert [p.fullname for p in listed] == ["Иван"]

    updated = await persons.update(person.id, notes="Любит настолки")
    assert updated is not None and updated.notes == "Любит настолки"

    assert await persons.delete(person.id) is True
    assert await persons.get(person.id) is None
    assert await persons.delete(person.id) is False


async def test_person_birth_month_constraint(session: AsyncSession) -> None:
    users = UserRepository(session)
    await users.get_or_create(123)

    with raises(IntegrityError):
        session.add(Person(tg_id=123, fullname="Ошибка", birth_day=10, birth_month=13))
        await session.flush()


async def test_user_settings_defaults_and_crud(session: AsyncSession) -> None:
    users = UserRepository(session)
    settings = UserSettingRepository(session)
    await users.get_or_create(123)

    setting = await settings.create(123)

    assert setting.id is not None
    assert setting.notify_days_before == 7
    assert setting.notification_time == time(9, 0)
    assert setting.is_enabled is True
    assert setting.user.tg_id == 123

    updated = await settings.update(setting.id, notify_days_before=3, is_enabled=False)
    assert updated is not None
    assert updated.notify_days_before == 3
    assert updated.is_enabled is False

    assert await settings.delete(setting.id) is True
    assert await settings.list_by_user(123) == []
