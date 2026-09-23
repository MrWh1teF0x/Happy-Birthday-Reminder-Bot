from unittest.mock import AsyncMock

from src.handlers.commands import BOT_COMMANDS, setup_commands


async def test_setup_commands_registers_all_commands() -> None:
    bot = AsyncMock()

    await setup_commands(bot)

    bot.set_my_commands.assert_awaited_once()
    registered = bot.set_my_commands.await_args.args[0]
    assert [command.command for command in registered] == [
        "start",
        "add_birthday",
        "birthdays_list",
        "edit_birthday",
        "reminders_list",
        "add_reminder",
        "edit_reminder",
        "edit_utc",
    ]


def test_command_names_are_valid_for_telegram() -> None:
    for command in BOT_COMMANDS:
        assert command.command == command.command.lower().replace(" ", "")
        assert len(command.command) <= 32
        assert command.description
