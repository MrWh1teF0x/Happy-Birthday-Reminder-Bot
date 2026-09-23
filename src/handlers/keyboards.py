from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Все часовые пояса России: подпись кнопки -> представительная зона IANA.
UTC_OFFSET_TIMEZONES: tuple[tuple[str, str], ...] = (
    ("UTC +2 (Калининград)", "Europe/Kaliningrad"),
    ("UTC +3 (Москва, Минск)", "Europe/Moscow"),
    ("UTC +4 (Самара, Баку, Ереван)", "Europe/Samara"),
    ("UTC +5 (Екатеринбург, Ташкент)", "Asia/Yekaterinburg"),
    ("UTC +6 (Омск, Астана)", "Asia/Omsk"),
    ("UTC +7 (Новосибирск, Красноярск)", "Asia/Krasnoyarsk"),
    ("UTC +8 (Иркутск)", "Asia/Irkutsk"),
    ("UTC +9 (Якутск, Чита)", "Asia/Yakutsk"),
    ("UTC +10 (Владивосток, Хабаровск)", "Asia/Vladivostok"),
    ("UTC +11 (Магадан, Южно-Сахалинск)", "Asia/Magadan"),
    ("UTC +12 (Камчатка, Анадырь)", "Asia/Kamchatka"),
)

TIMEZONE_CALLBACK_PREFIX = "tz:"


def build_timezone_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{TIMEZONE_CALLBACK_PREFIX}{zone}")]
        for label, zone in UTC_OFFSET_TIMEZONES
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
