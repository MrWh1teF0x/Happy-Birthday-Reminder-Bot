"""Меню команд бота (подсказки при вводе /)."""

from aiogram import Bot
from aiogram.types import BotCommand

BOT_COMMANDS: tuple[BotCommand, ...] = (
    BotCommand(command="start", description="Начать работу и выбрать часовой пояс"),
    BotCommand(command="help", description="Показать все команды"),
    BotCommand(command="add_birthday", description="Добавить день рождения"),
    BotCommand(command="birthdays_list", description="Показать все сохранённые дни рождения"),
    BotCommand(command="edit_birthday", description="Изменить день рождения"),
    BotCommand(command="reminders_list", description="Показать все оповещения"),
    BotCommand(command="add_reminder", description="Добавить оповещение"),
    BotCommand(command="edit_reminder", description="Изменить оповещение"),
    BotCommand(command="edit_utc", description="Изменить часовой пояс"),
)


def render_help() -> str:
    return (
        "🛠 Что я умею и какие есть команды:\n"
        "\n"
        "⚙️ Основные\n"
        "🔹 /start — Перезапустить бота и настроить часовой пояс\n"
        "🔹 /help — Показать это меню с командами\n"
        "🔹 /edit_utc — Изменить свой часовой пояс\n"
        "\n"
        "🎂 Дни рождения\n"
        "🔹 /add_birthday — Добавить новый день рождения\n"
        "🔹 /birthdays_list — Посмотреть весь список именинников\n"
        "🔹 /edit_birthday — Изменить или удалить день рождения\n"
        "\n"
        "🔔 Уведомления\n"
        "🔹 /add_reminder — Настроить время и интервалы напоминаний\n"
        "🔹 /reminders_list — Посмотреть активные оповещения\n"
        "🔹 /edit_reminder — Изменить настройки оповещений"
    )


async def setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(list(BOT_COMMANDS))
