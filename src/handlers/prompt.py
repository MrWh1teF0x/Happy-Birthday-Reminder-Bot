"""Чистый UI шагов: удаление промптов и предупреждения поверх них."""

from contextlib import suppress

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

INVALID_VALUES_WARNING = "⚠️ Введены некорректные значения."


async def delete_step_message(bot: Bot, chat_id: int, state: FSMContext, key: str) -> None:
    data = await state.get_data()
    prompt_id = data.get(key)
    if isinstance(prompt_id, int):
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, prompt_id)


async def cleanup_step(message: Message, state: FSMContext, key: str) -> None:
    """Удаляет текст пользователя и предыдущий промпт бота для чистого UI."""
    with suppress(TelegramBadRequest):
        await message.delete()
    if message.bot is not None:
        await delete_step_message(message.bot, message.chat.id, state, key)


async def warn_invalid_input(
    message: Message, state: FSMContext, key: str, original_text: str
) -> None:
    """Удаляет ввод пользователя и дописывает предупреждение в начало промпта.

    Текст промпта и его кнопки остаются нетронутыми.
    """
    with suppress(TelegramBadRequest):
        await message.delete()
    if message.bot is None:
        return
    data = await state.get_data()
    prompt_id = data.get(key)
    if not isinstance(prompt_id, int):
        await message.answer(INVALID_VALUES_WARNING)
        return
    with suppress(TelegramBadRequest):
        await message.bot.edit_message_text(
            f"{INVALID_VALUES_WARNING}\n\n{original_text}",
            chat_id=message.chat.id,
            message_id=prompt_id,
            parse_mode="Markdown",
        )
