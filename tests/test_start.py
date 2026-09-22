from unittest.mock import AsyncMock, MagicMock

from src.handlers import router, start_handler


async def test_start_handler_greets_user_by_name() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user.full_name = "Тест"

    await start_handler(message)

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Тест" in text


async def test_start_handler_without_user() -> None:
    message = MagicMock()
    message.answer = AsyncMock()
    message.from_user = None

    await start_handler(message)

    message.answer.assert_awaited_once()


def test_start_handler_is_registered_for_command_start() -> None:
    callbacks = [handler.callback.__name__ for handler in router.message.handlers]
    assert "start_handler" in callbacks
