"""Таблица user_settings: настройки уведомлений пользователя."""

from datetime import time
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database.models.base import Base

if TYPE_CHECKING:
    from src.database.models.user import User


class UserSetting(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True
    )
    notify_days_before: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    notification_time: Mapped[time] = mapped_column(Time, nullable=False, default=time(9, 0))
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    user: Mapped["User"] = relationship(back_populates="settings", lazy="selectin")
