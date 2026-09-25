from datetime import date

from src.handlers.birthday_notify import (
    NTF_HIDE,
    NTF_NOTE_PREFIX,
    build_birthday_notification,
    build_notification_keyboard,
)

TODAY = date(2026, 9, 5)


def test_future_reminder_with_year_and_note() -> None:
    text = build_birthday_notification(
        fullname="Алексей",
        day=12,
        month=9,
        year=1995,
        note="Дарить книги",
        days_before=7,
        today=TODAY,
    )

    assert "🔔 **Напоминание о дне рождения!**" in text
    assert "Через **7 дней** (12 сентября)" in text
    assert "👤 **Алексей**" in text
    assert "🎂 Исполнится: **31 год**" in text
    assert "🎁 *Заметка: Дарить книги*" in text
    assert "Самое время подготовить подарок" in text


def test_today_birthday() -> None:
    text = build_birthday_notification(
        fullname="Мама",
        day=5,
        month=9,
        year=1984,
        note=None,
        days_before=0,
        today=TODAY,
    )

    assert "🎉 **СЕГОДНЯ ДЕНЬ РОЖДЕНИЯ!**" in text
    assert "🎈 Сегодня свой день рождения отмечает:" in text
    assert "🎂 Исполнилось: **42 года**" in text
    assert "Не забудьте поздравить именинника" in text
    assert "Заметка" not in text


def test_tomorrow_branch() -> None:
    text = build_birthday_notification(
        fullname="Папа",
        day=6,
        month=9,
        year=None,
        note=None,
        days_before=1,
        today=TODAY,
    )

    assert "🗓 **Завтра** свой день рождения отмечает:" in text
    assert "Исполн" not in text


def test_day_forms_plural() -> None:
    for days, word in ((2, "2 дня"), (3, "3 дня"), (5, "5 дней"), (21, "21 день")):
        text = build_birthday_notification(
            fullname="X",
            day=1,
            month=1,
            year=None,
            note=None,
            days_before=days,
            today=TODAY,
        )
        assert f"Через **{word}**" in text


def test_notification_keyboard() -> None:
    keyboard = build_notification_keyboard(101)

    row = keyboard.inline_keyboard[0]
    assert row[0].text == "📝 Изменить заметку"
    assert row[0].callback_data == f"{NTF_NOTE_PREFIX}101"
    assert row[1].text == "❌ Скрыть"
    assert row[1].callback_data == NTF_HIDE
