from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

POPULAR_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("Калининград", "Europe/Kaliningrad"),
    ("Москва", "Europe/Moscow"),
    ("Самара", "Europe/Samara"),
    ("Екатеринбург", "Asia/Yekaterinburg"),
    ("Новосибирск", "Asia/Novosibirsk"),
    ("Владивосток", "Asia/Vladivostok"),
    ("Камчатка", "Asia/Kamchatka"),
    ("Минск", "Europe/Minsk"),
    ("Алматы", "Asia/Almaty"),
    ("Ташкент", "Asia/Tashkent"),
    ("UTC", "UTC"),
)

TIMEZONE_CALLBACK_PREFIX = "tz:"


def build_timezone_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for label, zone in POPULAR_TIMEZONES:
        row.append(
            InlineKeyboardButton(text=label, callback_data=f"{TIMEZONE_CALLBACK_PREFIX}{zone}")
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)
