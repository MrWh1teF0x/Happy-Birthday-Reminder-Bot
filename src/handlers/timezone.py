"""Выбор часового пояса: кнопки + свободный ввод, используется /start и edit_utc."""

from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository, UserSettingRepository
from src.handlers.keyboards import TIMEZONE_CALLBACK_PREFIX, build_timezone_keyboard
from src.handlers.states import TimezoneStates

router = Router(name="timezone")


def is_valid_timezone(zone: str) -> bool:
    try:
        ZoneInfo(zone)
    except Exception:
        return False
    return True


async def save_timezone_and_seed_reminder(db: AsyncSession, tg_id: int, zone: str) -> None:
    """Сохраняет зону и создаёт оповещение «за 7 дней в 09:00», если их ещё нет."""
    users = UserRepository(db)
    if await users.get_by_tg_id(tg_id) is None:
        raise ValueError(f"user {tg_id} is not registered")
    await users.set_time_zone(tg_id, zone)
    settings = UserSettingRepository(db)
    if not await settings.list_by_user(tg_id):
        await settings.create(tg_id)


async def request_timezone(message: Message, current: str | None = None) -> None:
    text = (
        "Выбери свой часовой пояс (кнопки ниже) или пришли название из базы IANA — "
        "например, `Europe/Moscow`."
    )
    if current:
        text = f"Текущий часовой пояс: `{current}`.\n\n{text}"
    await message.answer(text, reply_markup=build_timezone_keyboard(), parse_mode="Markdown")


@router.callback_query(
    TimezoneStates.waiting_for_timezone, F.data.startswith(TIMEZONE_CALLBACK_PREFIX)
)
async def timezone_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    zone = (callback.data or "").removeprefix(TIMEZONE_CALLBACK_PREFIX)
    if not is_valid_timezone(zone) or callback.from_user is None:
        await callback.answer("Неизвестный часовой пояс.", show_alert=True)
        return
    await save_timezone_and_seed_reminder(db, callback.from_user.id, zone)
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Готово! Часовой пояс — `{zone}`. Буду присылать оповещения за 7 дней в 09:00. "
            "Посмотреть и изменить оповещения: /reminders_list.",
            parse_mode="Markdown",
        )


@router.message(TimezoneStates.waiting_for_timezone, F.text)
async def timezone_text_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    zone = (message.text or "").strip()
    if not is_valid_timezone(zone) or message.from_user is None:
        await message.answer(
            "Не знаю такой часовой пояс. Пришли название из базы IANA — например, `Europe/Moscow`.",
            parse_mode="Markdown",
        )
        return
    await save_timezone_and_seed_reminder(db, message.from_user.id, zone)
    await state.clear()
    await message.answer(
        f"Готово! Часовой пояс — `{zone}`. Буду присылать оповещения за 7 дней в 09:00. "
        "Посмотреть и изменить оповещения: /reminders_list.",
        parse_mode="Markdown",
    )
