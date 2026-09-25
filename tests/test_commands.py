from unittest.mock import AsyncMock, MagicMock

from src.handlers.commands import BOT_COMMANDS, render_help, setup_commands
from src.handlers.help import help_handler
from src.handlers.help import router as help_router


async def test_setup_commands_registers_all_commands() -> None:
    bot = AsyncMock()

    await setup_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    registered = bot.set_my_commands.await_args.args[0]
    assert [command.command for command in registered] == [
        "start",
        "help",
        "add_birthday",
        "birthdays_list",
        "edit_birthday",
        "reminders_list",
        "add_reminder",
        "edit_reminder",
        "edit_utc",
    ]


def test_render_help_lists_all_commands() -> None:
    text = render_help()

    for command in BOT_COMMANDS:
        assert f"/{command.command}" in text
    assert "⚙️ Основные" in text
    assert "🎂 Дни рождения" in text
    assert "🔔 Уведомления" in text


def test_command_names_are_valid_for_telegram() -> None:
    for command in BOT_COMMANDS:
        assert command.command == command.command.lower().replace(" ", "")
        assert len(command.command) <= 32
        assert command.description


async def test_help_handler_shows_all_commands() -> None:
    from src.handlers import router

    message = MagicMock()
    message.answer = AsyncMock()

    await help_handler(message)

    text = message.answer.await_args.args[0]
    assert "/add_birthday" in text
    assert "/reminders_list" in text
    assert "/help" in text
    assert help_router in router.sub_routers
