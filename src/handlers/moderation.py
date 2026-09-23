"""Модерация: молча удаляет нетекст, на любой прочий текст отвечает про команды.

Роутер подключается последним, поэтому срабатывает только если ни один
другой хендлер не подошёл (ввод в FSM-формах перехватывается раньше).
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


async def delete_quietly(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.message(~F.text)
async def non_text_handler(message: Message) -> None:
    await delete_quietly(message)


@router.message(F.text.func(contains_emoji))
async def emoji_text_handler(message: Message) -> None:
    await delete_quietly(message)


@router.message(F.text)
async def unknown_command_handler(message: Message) -> None:
    await message.answer("Такой команды не существует.\n\nДоступные команды:\n" + COMMANDS_HINT)
