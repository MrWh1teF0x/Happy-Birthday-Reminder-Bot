from unittest.mock import AsyncMock, MagicMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import DeleteMessage

from src.handlers import router
from src.handlers.moderation import (
    contains_emoji,
    emoji_text_handler,
    non_text_handler,
    unknown_command_handler,
)
from src.handlers.moderation import router as moderation_router


def make_message(text: str | None) -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    message.text = text
    return message


async def test_non_text_message_is_deleted() -> None:
    message = make_message(None)

    await non_text_handler(message)

    message.delete.assert_awaited_once()
    message.answer.assert_awaited_once()


async def test_non_text_delete_failure_still_warns() -> None:
    message = make_message(None)
    message.delete = AsyncMock(
        side_effect=TelegramBadRequest(method=DeleteMessage(chat_id=1, message_id=1), message="x")
    )

    await non_text_handler(message)

    message.answer.assert_awaited_once()


async def test_emoji_text_is_deleted() -> None:
    message = make_message("Привет 🎂")

    await emoji_text_handler(message)

    message.delete.assert_awaited_once()


async def test_unknown_command_lists_available_commands() -> None:
    message = make_message("/несуществует")

    await unknown_command_handler(message)

    text = message.answer.await_args.args[0]
    assert "не существует" in text
    assert "/add_birthday" in text
    assert "/reminders_list" in text


def test_contains_emoji() -> None:
    assert contains_emoji("Привет 🎂") is True
    assert contains_emoji("Обычный текст") is False


def test_moderation_router_is_last() -> None:
    assert router.sub_routers[-1] is moderation_router
