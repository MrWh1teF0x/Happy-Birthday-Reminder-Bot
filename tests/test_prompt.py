from unittest.mock import AsyncMock, MagicMock

from src.handlers.prompt import INVALID_VALUES_WARNING, warn_invalid_input


def make_message(text: str) -> MagicMock:
    message = MagicMock()
    message.answer = AsyncMock()
    message.delete = AsyncMock()
    message.text = text
    message.chat.id = 123
    message.bot.delete_message = AsyncMock()
    message.bot.edit_message_text = AsyncMock()
    return message


def make_state(data: dict[str, object] | None = None) -> AsyncMock:
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=data or {})
    return state


async def test_warn_prepends_warning_keeping_prompt() -> None:
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    message = make_message("билеберда")
    state = make_state({"key": 42})
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data="x")]]
    )

    await warn_invalid_input(message, state, "key", "Оригинальный текст", keyboard)

    message.delete.assert_awaited_once()
    edited = message.bot.edit_message_text.await_args
    assert edited.args[0] == f"{INVALID_VALUES_WARNING}\n\nОригинальный текст"
    assert edited.kwargs["reply_markup"] is keyboard


async def test_warn_without_prompt_sends_plain_warning() -> None:
    message = make_message("билеберда")
    state = make_state()

    await warn_invalid_input(message, state, "key", "Оригинальный текст")

    message.bot.edit_message_text.assert_not_awaited()
    message.answer.assert_awaited_once_with(INVALID_VALUES_WARNING)
