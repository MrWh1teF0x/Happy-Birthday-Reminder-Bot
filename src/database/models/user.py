"""Таблица users: владельцы записей (пользователи Telegram)."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base

if TYPE_CHECKING:
    from src.database.models.person import Person
    from src.database.models.user_setting import UserSetting


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    time_zone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    tz_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    help_shown: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    persons: Mapped[list["Person"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", lazy="selectin"
    )
    settings: Mapped[list["UserSetting"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )
