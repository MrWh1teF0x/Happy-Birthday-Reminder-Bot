"""Модерация: удаляет всё, кроме чистого текста, и отвечает на неизвестные команды.

Роутер подключается последним, поэтому срабатывает только если ни один
другой хендлер не подошёл.
"""

import emoji
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from src.handlers.commands import BOT_COMMANDS

router = Router(name="moderation")

COMMANDS_HINT = ", ".join(f"/{command.command}" for command in BOT_COMMANDS)


def contains_emoji(text: str) -> bool:
    return emoji.emoji_count(text) > 0


async def delete_with_warning(message: Message, warning: str) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass
    await message.answer(warning)


@router.message(~F.text)
async def non_text_handler(message: Message) -> None:
    await delete_with_warning(message, "Принимаю только текстовые сообщения — остальное удаляю.")


@router.message(F.text.func(contains_emoji))
async def emoji_text_handler(message: Message) -> None:
    await delete_with_warning(
        message, "Сообщения со смайликами удаляю — пришли, пожалуйста, обычный текст."
    )


@router.message(F.text.startswith("/"))
async def unknown_command_handler(message: Message) -> None:
    await message.answer("Такой команды не существует.\n\nДоступные команды:\n" + COMMANDS_HINT)
