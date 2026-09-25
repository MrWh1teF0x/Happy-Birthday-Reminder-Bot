"""Таблица sent_notifications_log: защита от повторной отправки за день."""

from datetime import date as date_type
from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.database.models.base import Base


class SentNotification(Base):
    __tablename__ = "sent_notifications_log"
    __table_args__ = (
        UniqueConstraint(
            "tg_id",
            "person_id",
            "setting_id",
            "notify_date",
            name="uq_sent_notification",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    setting_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("user_settings.id", ondelete="CASCADE"), nullable=False
    )
    notify_date: Mapped[date_type] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
