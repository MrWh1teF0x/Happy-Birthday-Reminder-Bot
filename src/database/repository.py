"""Репозитории: доступ к users, persons, user_settings через AsyncSession.

Репозитории не делают commit — транзакцией управляет вызывающий код.
"""

from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Person, User, UserSetting


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_tg_id(self, tg_id: int) -> User | None:
        result = await self._session.execute(select(User).where(User.tg_id == tg_id))
        return result.scalar_one_or_none()

    async def get_or_create(
        self, tg_id: int, *, username: str | None = None, time_zone: str = "UTC"
    ) -> User:
        user = await self.get_by_tg_id(tg_id)
        if user is None:
            user = User(tg_id=tg_id, username=username, time_zone=time_zone)
            self._session.add(user)
            await self._session.flush()
            await self._session.refresh(user)
        elif username is not None and user.username != username:
            user.username = username
            await self._session.flush()
        return user

    async def set_time_zone(self, tg_id: int, time_zone: str) -> User | None:
        user = await self.get_by_tg_id(tg_id)
        if user is None:
            return None
        user.time_zone = time_zone
        user.tz_confirmed = True
        await self._session.flush()
        return user


class PersonRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_owner(self, tg_id: int) -> list[Person]:
        result = await self._session.execute(
            select(Person)
            .where(Person.tg_id == tg_id)
            .order_by(Person.birth_month, Person.birth_day)
        )
        return list(result.scalars().all())

    async def get(self, person_id: int) -> Person | None:
        result = await self._session.execute(select(Person).where(Person.id == person_id))
        return result.scalar_one_or_none()

    async def create(
        self,
        tg_id: int,
        *,
        fullname: str,
        birth_day: int,
        birth_month: int,
        birth_year: int | None = None,
        username: str | None = None,
        notes: str | None = None,
    ) -> Person:
        person = Person(
            tg_id=tg_id,
            fullname=fullname,
            birth_day=birth_day,
            birth_month=birth_month,
            birth_year=birth_year,
            username=username,
            notes=notes,
        )
        self._session.add(person)
        await self._session.flush()
        await self._session.refresh(person)
        return person

    async def update(self, person_id: int, **fields: Any) -> Person | None:
        person = await self.get(person_id)
        if person is None:
            return None
        for name, value in fields.items():
            setattr(person, name, value)
        await self._session.flush()
        await self._session.refresh(person)
        return person

    async def delete(self, person_id: int) -> bool:
        person = await self.get(person_id)
        if person is None:
            return False
        await self._session.delete(person)
        await self._session.flush()
        return True


class UserSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, tg_id: int) -> list[UserSetting]:
        result = await self._session.execute(select(UserSetting).where(UserSetting.tg_id == tg_id))
        return list(result.scalars().all())

    async def get(self, setting_id: int) -> UserSetting | None:
        result = await self._session.execute(
            select(UserSetting).where(UserSetting.id == setting_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        tg_id: int,
        *,
        notify_days_before: int = 7,
        notification_time: time = time(9, 0),
        is_enabled: bool = True,
    ) -> UserSetting:
        setting = UserSetting(
            tg_id=tg_id,
            notify_days_before=notify_days_before,
            notification_time=notification_time,
            is_enabled=is_enabled,
        )
        self._session.add(setting)
        await self._session.flush()
        await self._session.refresh(setting)
        return setting

    async def update(self, setting_id: int, **fields: Any) -> UserSetting | None:
        setting = await self.get(setting_id)
        if setting is None:
            return None
        for name, value in fields.items():
            setattr(setting, name, value)
        await self._session.flush()
        await self._session.refresh(setting)
        return setting

    async def delete(self, setting_id: int) -> bool:
        setting = await self.get(setting_id)
        if setting is None:
            return False
        await self._session.delete(setting)
        await self._session.flush()
        return True
