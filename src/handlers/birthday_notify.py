"""Генератор текста уведомлений о днях рождения.

Чистые функции: по данным именинника и интервалу строят текст сообщения
и клавиатуру. Отправкой займётся планировщик.
"""

from datetime import date

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.handlers.pagination import MONTHS_GENITIVE, next_occurrence, plural

NTF_NOTE_PREFIX = "ntf_note:"
NTF_HIDE = "ntf_hide"


def build_birthday_notification(
    *,
    fullname: str,
    day: int,
    month: int,
    year: int | None,
    note: str | None,
    days_before: int,
    today: date,
) -> str:
    """Собрать текст уведомления. days_before: 0 — день рождения сегодня."""
    if days_before == 0:
        header = "🎉 **СЕГОДНЯ ДЕНЬ РОЖДЕНИЯ!**"
        interval = "🎈 Сегодня свой день рождения отмечает:"
        age_verb = "Исполнилось"
        footer = "───\n📱 *Не забудьте поздравить именинника! ✨*"
    else:
        header = "🔔 **Напоминание о дне рождения!**"
        if days_before == 1:
            interval = "🗓 **Завтра** свой день рождения отмечает:"
        else:
            date_text = f"{day} {MONTHS_GENITIVE[month - 1]}"
            interval = (
                f"🗓 Через **{days_before} {plural(days_before, 'день', 'дня', 'дней')}** "
                f"({date_text}) день рождения отмечает:"
            )
        age_verb = "Исполнится"
        footer = "───\n💡 *Самое время подготовить подарок!*"

    lines = [header, "", interval, f"👤 **{fullname}**"]
    if year is not None:
        age = next_occurrence(day, month, today).year - year
        lines.append(f"🎂 {age_verb}: **{age} {plural(age, 'год', 'года', 'лет')}**")
    if note:
        lines.append(f"🎁 *Заметка: {note}*")
    lines.extend(["", footer])
    return "\n".join(lines)


def build_notification_keyboard(person_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Изменить заметку",
                    callback_data=f"{NTF_NOTE_PREFIX}{person_id}",
                ),
                InlineKeyboardButton(text="❌ Скрыть", callback_data=NTF_HIDE),
            ]
        ]
    )
