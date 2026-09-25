from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Все часовые пояса России: подпись кнопки -> представительная зона IANA.
UTC_OFFSET_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("MSK-1 (UTC+2) — Калининград", "Europe/Kaliningrad"),
    (
        "MSK (UTC+3) — Москва, Санкт-Петербург, Нижний Новгород, Казань, "
        "Ростов-на-Дону, Воронеж, Краснодар",
        "Europe/Moscow",
    ),
    ("MSK+1 (UTC+4) — Самара, Саратов, Ульяновск, Ижевск", "Europe/Samara"),
    ("MSK+2 (UTC+5) — Екатеринбург, Челябинск, Уфа, Пермь, Тюмень", "Asia/Yekaterinburg"),
    ("MSK+3 (UTC+6) — Омск", "Asia/Omsk"),
    (
        "MSK+4 (UTC+7) — Новосибирск, Красноярск, Барнаул, Томск, Кемерово",
        "Asia/Krasnoyarsk",
    ),
    ("MSK+5 (UTC+8) — Иркутск, Улан-Удэ", "Asia/Irkutsk"),
    ("MSK+6 (UTC+9) — Якутск, Чита", "Asia/Yakutsk"),
    ("MSK+7 (UTC+10) — Владивосток, Хабаровск", "Asia/Vladivostok"),
    ("MSK+8 (UTC+11) — Магадан, Южно-Сахалинск", "Asia/Magadan"),
    ("MSK+9 (UTC+12) — Петропавловск-Камчатский", "Asia/Kamchatka"),
)

TIMEZONE_CALLBACK_PREFIX = "tz:"


def build_timezone_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{TIMEZONE_CALLBACK_PREFIX}{zone}")]
        for label, zone in UTC_OFFSET_TIMEZONES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
