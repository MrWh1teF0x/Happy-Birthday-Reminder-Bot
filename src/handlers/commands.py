"""Меню команд бота (подсказки при вводе /)."""

from aiogram import Bot
from aiogram.types import BotCommand

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Начать работу и выбрать часовой пояс"),
    BotCommand(command="add_birthday", description="Добавить день рождения"),
    BotCommand(command="birthdays_list", description="Показать все сохранённые дни рождения"),
    BotCommand(command="edit_birthday", description="Изменить день рождения"),
    BotCommand(command="reminders_list", description="Показать все оповещения"),
    BotCommand(command="add_reminder", description="Добавить оповещение"),
    BotCommand(command="edit_reminder", description="Изменить оповещение"),
    BotCommand(command="edit_utc", description="Изменить часовой пояс"),
)


async def setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(BOT_COMMANDS))
