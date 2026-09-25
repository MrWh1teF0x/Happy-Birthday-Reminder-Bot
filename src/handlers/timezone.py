"""Выбор часового пояса: кнопки + свободный ввод, используется /start и edit_utc."""

from contextlib import suppress
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
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


async def save_timezone_and_seed_reminder(
    db: AsyncSession, tg_id: int, zone: str, username: str | None = None
) -> bool:
    """Сохраняет зону и создаёт оповещение «за 7 дней в 09:00», если их ещё нет.

    Возвращает True, если пояс выбран впервые (до этого не был подтверждён).
    """
    users = UserRepository(db)
    existing = await users.get_or_create(tg_id, username=username)
    is_first_choice = not existing.tz_confirmed
    await users.set_time_zone(tg_id, zone)
    settings = UserSettingRepository(db)
    if not await settings.list_by_user(tg_id):
        await settings.create(tg_id)
    return is_first_choice


async def request_timezone(message: Message, state: FSMContext, current: str | None = None) -> None:
    text = (
        "🕒 Выбери свой часовой пояс от UTC (кнопки ниже) "
        "или пришли название из базы IANA — например, `Europe/Moscow`."
    )
    if current:
        text = f"Текущий часовой пояс: `{current}`.\n\n{text}"
    sent = await message.answer(text, reply_markup=build_timezone_keyboard(), parse_mode="Markdown")
    await state.update_data(tz_prompt_id=sent.message_id)


def build_timezone_confirm_text(zone: str) -> str:
    return (
        f"Готово! Часовой пояс — `{zone}`. Буду присылать оповещения за 7 дней в 09:00. "
        "Посмотреть и изменить оповещения: /reminders_list."
    )


async def delete_timezone_prompt(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    prompt_id = data.get("tz_prompt_id")
    if isinstance(prompt_id, int):
        with suppress(TelegramBadRequest):
            await bot.delete_message(chat_id, prompt_id)


@router.message(Command("edit_utc"))
async def edit_utc_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    user = await UserRepository(db).get_or_create(
        message.from_user.id, username=message.from_user.username
    )
    await state.set_state(TimezoneStates.waiting_for_timezone)
    await request_timezone(message, state, current=user.time_zone)


# Без фильтра состояния: кнопка должна срабатывать, даже если бот
# перезапускался и FSM-состояние слетело.
@router.callback_query(F.data.startswith(TIMEZONE_CALLBACK_PREFIX))
async def timezone_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    zone = (callback.data or "").removeprefix(TIMEZONE_CALLBACK_PREFIX)
    if not is_valid_timezone(zone) or callback.from_user is None:
        await callback.answer("Неизвестный часовой пояс.", show_alert=True)
        return
    await callback.answer()
    await save_timezone_and_seed_reminder(
        db, callback.from_user.id, zone, username=callback.from_user.username
    )
    await state.clear()
    if isinstance(callback.message, Message):
        with suppress(TelegramBadRequest):
            await callback.message.delete()
        await callback.message.answer(build_timezone_confirm_text(zone), parse_mode="Markdown")


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
    if message.bot is not None:
        await delete_timezone_prompt(message.bot, message.chat.id, state)
    await state.clear()
    with suppress(TelegramBadRequest):
        await message.delete()
    await message.answer(build_timezone_confirm_text(zone), parse_mode="Markdown")
