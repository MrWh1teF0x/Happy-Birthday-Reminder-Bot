"""Middleware: блокирует команды, пока пользователь не выбрал часовой пояс."""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository
from src.handlers.keyboards import TIMEZONE_CALLBACK_PREFIX

ONBOARDING_PROMPT = "Сначала выбери часовой пояс — нажми /start."


def is_start_command(message: Message) -> bool:
    words = (message.text or "").split()
    if not words:
        return False
    return words[0].split("@")[0] == "/start"


class OnboardingMiddleware(BaseMiddleware):
    """Пропускает /start, кнопки пояса и обычный текст, остальное — только
    после подтверждения часового пояса (users.tz_confirmed)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id: int | None = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            if is_start_command(event):
                return await handler(event, data)
            # Обычный текст не блокируем: ввод зоны проверяет
            # timezone_text_handler, остальное — модерация.
            if event.text is None or not event.text.startswith("/"):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            if (event.data or "").startswith(TIMEZONE_CALLBACK_PREFIX):
                return await handler(event, data)
        else:
            return await handler(event, data)

        db = data.get("db")
        if user_id is None or not isinstance(db, AsyncSession):
            return await handler(event, data)
        user = await UserRepository(db).get_by_tg_id(user_id)
        if user is not None and user.tz_confirmed:
            return await handler(event, data)
        if isinstance(event, Message):
            await event.answer(ONBOARDING_PROMPT)
        else:
            await event.answer(ONBOARDING_PROMPT, show_alert=True)
        return None
