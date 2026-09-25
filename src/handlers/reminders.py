"""Оповещения: список, добавление и изменение (за сколько дней и во сколько)."""

import re
from contextlib import suppress
from datetime import datetime
from datetime import time as time_type
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository, UserSettingRepository
from src.database.models import UserSetting
from src.handlers.pagination import (
    build_pagination_keyboard,
    page_slice,
    paginate,
    plural,
)
from src.handlers.prompt import (
    INVALID_TIME_WARNING,
    cleanup_step,
    warn_invalid_input,
)
from src.handlers.reminder_saver import DbReminderSaver
from src.handlers.states import AddReminderSG, EditReminderStates

router = Router(name="reminders")

REM_PAGE_PREFIX = "rem_page"
EDIT_REM_PREFIX = "edit_rem:"
DEL_REM_PREFIX = "del_rem:"
CONFIRM_DEL_REM_PREFIX = "confirm_del_rem:"
CANCEL_DEL_REM = "cancel_del_rem"
FIELD_DAYS = "days"
FIELD_TIME = "time"
REM_PAGE_KEY = "rem_page"
TIME_EDIT_PROMPT_KEY = "time_edit_prompt_id"
EDIT_REM_CANCEL = "edit_rem:cancel"

ADD_PREFIX = "rem_add:"
ADD_DAYS_PREFIX = "rem_add:days:"
ADD_TIME_PREFIX = "rem_add:time:"
ADD_NEW = "rem_add:new"
ADD_ALL = "rem_add:all"
ADD_BACK = "rem_add:back"
ADD_CANCEL = "rem_add:cancel"

DAY_OPTIONS: tuple[tuple[str, int], ...] = (
    ("🎉 В день праздника (0)", 0),
    ("⚡ За 1 день", 1),
    ("🗓 За 3 дня", 3),
    ("📆 За 7 дней", 7),
)

TIME_OPTIONS: tuple[str, ...] = ("09:00", "12:00", "18:00", "21:00")
TIME_LABELS: dict[str, str] = {
    "09:00": "🌅 09:00",
    "12:00": "☀️ 12:00",
    "18:00": "🌆 18:00",
    "21:00": "🌙 21:00",
}

STEP1_TEXT = (
    "🔔 **Шаг 1 из 2: За сколько дней отправлять уведомление?**\n"
    "\n"
    "Выберите вариант или напишите число дней текстом (например: `14`):"
)

STEP2_TEXT = (
    "⏰ **Шаг 2 из 2: Время отправки**\n"
    "\n"
    "Выберите время или напишите его текстом в формате ЧЧ:ММ (например: `09:30`):"
)

DAYS_PROMPT_KEY = "days_prompt_id"
TIME_PROMPT_KEY = "time_prompt_id"

EMPTY_REM_TEXT = "🔔 У вас нет настроенных напоминаний."

_TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*$")
MAX_DAYS_BEFORE = 365


def parse_days(text: str) -> int | None:
    try:
        days = int(text.strip())
    except ValueError:
        return None
    if 0 <= days <= MAX_DAYS_BEFORE:
        return days
    return None


def parse_time(text: str) -> time_type | None:
    match = _TIME_RE.match(text)
    if match is None:
        return None
    try:
        return time_type(int(match.group(1)), int(match.group(2)))
    except ValueError:
        return None


def format_reminder(setting: UserSetting) -> str:
    status = "включено ✅" if setting.is_enabled else "выключено ⏸"
    return (
        f"За {setting.notify_days_before} дн. "
        f"в {setting.notification_time.strftime('%H:%M')} — {status}"
    )


def utc_label(tz_name: str | None) -> str:
    try:
        offset = datetime.now(ZoneInfo(tz_name or "UTC")).utcoffset()
    except Exception:
        return "UTC"
    hours = int(offset.total_seconds() // 3600) if offset else 0
    return f"UTC{hours:+d}"


def format_days_full(days: int) -> str:
    if days == 0:
        return "В день праздника"
    return f"За {days} {plural(days, 'день', 'дня', 'дней')}"


def build_reminder_card(setting: UserSetting, index: int) -> str:
    days = format_days_full(setting.notify_days_before)
    time = setting.notification_time.strftime("%H:%M")
    return f"⏰ {index}. **{days}** — отправка в {time}"


def build_reminders_page_text(settings: list[UserSetting], page: int, utc: str) -> str:
    header = f"🔔 **Список напоминаний** *(Всего: {len(settings)}, {utc})*"
    offset = (page - 1) * 5
    cards = [
        build_reminder_card(setting, offset + i + 1)
        for i, setting in enumerate(settings[page_slice(page)])
    ]
    return header + "\n\n" + "\n\n".join(cards)


def build_reminders_page_keyboard(
    settings: list[UserSetting], page: int, total_pages: int
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"✏️ {setting.notify_days_before} дн",
                callback_data=f"{EDIT_REM_PREFIX}{setting.id}",
            ),
            InlineKeyboardButton(
                text=f"🗑 {setting.notify_days_before} дн",
                callback_data=f"{DEL_REM_PREFIX}{setting.id}",
            ),
        ]
        for setting in settings[page_slice(page)]
    ]
    nav = build_pagination_keyboard(REM_PAGE_PREFIX, page, total_pages, numbered_nav=True)
    if nav is not None:
        rows.extend(nav.inline_keyboard)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_delete_confirm_keyboard(setting_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, удалить",
                    callback_data=f"{CONFIRM_DEL_REM_PREFIX}{setting_id}",
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data=CANCEL_DEL_REM),
            ]
        ]
    )


async def get_rem_page(state: FSMContext) -> int:
    data = await state.get_data()
    try:
        return max(1, int(data.get(REM_PAGE_KEY, 1)))
    except (TypeError, ValueError):
        return 1


async def answer_reminders_page(
    message: Message, db: AsyncSession, tg_id: int, page: int, state: FSMContext
) -> None:
    user = await UserRepository(db).get_by_tg_id(tg_id)
    settings = await UserSettingRepository(db).list_by_user(tg_id)
    if not settings:
        await message.answer(EMPTY_REM_TEXT)
        return
    page, total_pages = paginate(len(settings), page)
    await state.update_data(rem_page=page)
    utc = utc_label(user.time_zone if user else None)
    await message.answer(
        build_reminders_page_text(settings, page, utc),
        reply_markup=build_reminders_page_keyboard(settings, page, total_pages),
        parse_mode="Markdown",
    )


async def edit_reminders_page(
    message: Message, db: AsyncSession, tg_id: int, page: int, state: FSMContext
) -> None:
    user = await UserRepository(db).get_by_tg_id(tg_id)
    settings = await UserSettingRepository(db).list_by_user(tg_id)
    if not settings:
        await message.edit_text(EMPTY_REM_TEXT)
        return
    page, total_pages = paginate(len(settings), page)
    await state.update_data(rem_page=page)
    utc = utc_label(user.time_zone if user else None)
    await message.edit_text(
        build_reminders_page_text(settings, page, utc),
        reply_markup=build_reminders_page_keyboard(settings, page, total_pages),
        parse_mode="Markdown",
    )


def build_days_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{ADD_DAYS_PREFIX}{days}")]
        for label, days in DAY_OPTIONS
    ]
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=ADD_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_time_keyboard() -> InlineKeyboardMarkup:
    times = list(TIME_LABELS.items())
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=f"{ADD_TIME_PREFIX}{moment}")
            for moment, label in times[i : i + 2]
        ]
        for i in range(0, len(times), 2)
    ]
    rows.append(
        [
            InlineKeyboardButton(text="◀️ Назад", callback_data=ADD_BACK),
            InlineKeyboardButton(text="❌ Отмена", callback_data=ADD_CANCEL),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_finish_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить еще", callback_data=ADD_NEW),
                InlineKeyboardButton(text="⚙️ Все настройки", callback_data=ADD_ALL),
            ]
        ]
    )


def format_interval(days: int) -> str:
    if days == 0:
        return "в день праздника"
    return f"за {days} дн."


def build_finish_text(setting: UserSetting) -> str:
    return (
        "✅ Напоминание сохранено: "
        f"{format_interval(setting.notify_days_before)} "
        f"в {setting.notification_time.strftime('%H:%M')}."
    )


async def get_owned_setting(db: AsyncSession, tg_id: int, setting_id: int) -> UserSetting | None:
    setting = await UserSettingRepository(db).get(setting_id)
    if setting is None or setting.tg_id != tg_id:
        return None
    return setting


@router.message(Command("reminders_list"))
async def reminders_list_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await answer_reminders_page(message, db, message.from_user.id, 1, state)


@router.callback_query(F.data.startswith(REM_PAGE_PREFIX + ":"))
async def reminders_page_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        return
    try:
        page = int(callback.data.split(":")[1])
    except (ValueError, IndexError):
        await callback.answer("Некорректная страница.", show_alert=True)
        return
    await callback.answer()
    await edit_reminders_page(callback.message, db, callback.from_user.id, page, state)


async def start_add_flow(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await UserRepository(db).get_or_create(
        message.from_user.id, username=message.from_user.username
    )
    await state.set_state(AddReminderSG.waiting_for_days)
    sent = await message.answer(
        STEP1_TEXT, reply_markup=build_days_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(days_prompt_id=sent.message_id)


@router.message(Command("add_reminder"))
async def add_reminder_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    await start_add_flow(message, db, state)


@router.callback_query(F.data == ADD_NEW)
async def reminder_add_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if callback.from_user is not None:
        await UserRepository(db).get_or_create(
            callback.from_user.id, username=callback.from_user.username
        )
    await state.set_state(AddReminderSG.waiting_for_days)
    await callback.message.edit_text(
        STEP1_TEXT, reply_markup=build_days_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(days_prompt_id=callback.message.message_id)


@router.callback_query(F.data.startswith(ADD_DAYS_PREFIX))
async def reminder_days_button_handler(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None or not isinstance(callback.message, Message):
        return
    try:
        days = int(callback.data.removeprefix(ADD_DAYS_PREFIX))
    except ValueError:
        await callback.answer("Некорректное число.", show_alert=True)
        return
    if parse_days(str(days)) is None:
        await callback.answer("Некорректное число.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(days=days)
    await state.set_state(AddReminderSG.waiting_for_time)
    await callback.message.edit_text(
        STEP2_TEXT, reply_markup=build_time_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(time_prompt_id=callback.message.message_id)


@router.message(AddReminderSG.waiting_for_days, F.text)
async def reminder_days_handler(message: Message, state: FSMContext) -> None:
    days = parse_days(message.text or "")
    if days is None:
        await warn_invalid_input(message, state, DAYS_PROMPT_KEY, STEP1_TEXT, build_days_keyboard())
        return
    await state.update_data(days=days)
    await state.set_state(AddReminderSG.waiting_for_time)
    await cleanup_step(message, state, DAYS_PROMPT_KEY)
    sent = await message.answer(
        STEP2_TEXT, reply_markup=build_time_keyboard(), parse_mode="Markdown"
    )
    await state.update_data(time_prompt_id=sent.message_id)


async def finish_add_reminder(
    db: AsyncSession, state: FSMContext, tg_id: int, moment: time_type, answer_to: Message
) -> None:
    data = await state.get_data()
    try:
        days = int(data["days"])
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await answer_to.answer("Что-то пошло не так. Начни заново: /add_reminder.")
        return
    setting = await DbReminderSaver(db).save_reminder(tg_id, days, moment)
    settings = await UserSettingRepository(db).list_by_user(tg_id)
    await state.clear()
    user = await UserRepository(db).get_by_tg_id(tg_id)
    utc = utc_label(user.time_zone if user else None)
    text = build_finish_text(setting) + "\n\n" + build_reminders_page_text(settings, 1, utc)
    await answer_to.answer(text, reply_markup=build_finish_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith(ADD_TIME_PREFIX))
async def reminder_time_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    moment = parse_time(callback.data.removeprefix(ADD_TIME_PREFIX))
    if moment is None or not isinstance(callback.message, Message):
        await callback.answer("Некорректное время.", show_alert=True)
        return
    await callback.answer()
    with suppress(TelegramBadRequest):
        await callback.message.delete()
    await finish_add_reminder(db, state, callback.from_user.id, moment, callback.message)


@router.message(AddReminderSG.waiting_for_time, F.text)
async def reminder_time_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    moment = parse_time(message.text or "")
    if moment is None:
        await warn_invalid_input(message, state, TIME_PROMPT_KEY, STEP2_TEXT, build_time_keyboard())
        return
    await cleanup_step(message, state, TIME_PROMPT_KEY)
    await finish_add_reminder(db, state, message.from_user.id, moment, message)


@router.callback_query(F.data == ADD_BACK)
async def reminder_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddReminderSG.waiting_for_days)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            STEP1_TEXT, reply_markup=build_days_keyboard(), parse_mode="Markdown"
        )
        await state.update_data(days_prompt_id=callback.message.message_id)


@router.callback_query(F.data == ADD_CANCEL)
async def reminder_cancel_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await edit_reminders_page(callback.message, db, callback.from_user.id, 1, state)


@router.callback_query(F.data == ADD_ALL)
async def reminder_all_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    page = await get_rem_page(state)
    await edit_reminders_page(callback.message, db, callback.from_user.id, page, state)


@router.message(Command("edit_reminder"))
async def edit_reminder_hint_handler(message: Message) -> None:
    await message.answer(
        "Чтобы изменить время оповещения, открой /reminders_list и нажми ⏰ под нужной записью."
    )


def build_time_edit_text(setting: UserSetting) -> str:
    current = setting.notification_time.strftime("%H:%M")
    return (
        f"⏰ Текущее время: **{current}**.\n\nПришли новое время в формате ЧЧ:ММ — например, 09:00."
    )


def build_time_edit_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="❌ Отмена", callback_data=EDIT_REM_CANCEL)]]
    )


@router.callback_query(F.data == EDIT_REM_CANCEL)
async def reminder_time_edit_cancel_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        page = await get_rem_page(state)
        await edit_reminders_page(callback.message, db, callback.from_user.id, page, state)


@router.callback_query(F.data.startswith(EDIT_REM_PREFIX))
async def reminder_time_edit_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(EDIT_REM_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.set_state(EditReminderStates.waiting_for_value)
    await state.update_data(setting_id=setting_id, field=FIELD_TIME)
    await callback.answer()
    await callback.message.edit_text(
        build_time_edit_text(setting),
        parse_mode="Markdown",
    )
    await state.update_data(time_edit_prompt_id=callback.message.message_id)


@router.message(EditReminderStates.waiting_for_value, F.text)
async def reminder_value_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    data = await state.get_data()
    setting = await get_owned_setting(db, message.from_user.id, int(data.get("setting_id", -1)))
    if setting is None:
        await state.clear()
        await message.answer("Запись не найдена. Открой /reminders_list и попробуй снова.")
        return
    field = data.get("field")
    value = (message.text or "").strip()
    if field == FIELD_DAYS:
        days = parse_days(value)
        if days is None:
            await message.answer("Нужно число от 0 до 365. Попробуй ещё раз.")
            return
        updates: dict[str, object] = {"notify_days_before": days}
    elif field == FIELD_TIME:
        moment = parse_time(value)
        if moment is None:
            await warn_invalid_input(
                message,
                state,
                TIME_EDIT_PROMPT_KEY,
                build_time_edit_text(setting),
                build_time_edit_cancel_keyboard(),
                INVALID_TIME_WARNING,
            )
            return
        updates = {"notification_time": moment}
    else:
        await state.clear()
        await message.answer("Неизвестное поле. Открой /reminders_list и попробуй снова.")
        return
    updated = await UserSettingRepository(db).update(setting.id, **updates)
    await state.clear()
    if updated is None:
        await message.answer("Не удалось сохранить. Попробуй снова: /reminders_list.")
        return
    await message.answer(f"Готово! {format_reminder(updated)}")


def build_reminder_delete_text(setting: UserSetting) -> str:
    days = format_days_full(setting.notify_days_before)
    time = setting.notification_time.strftime("%H:%M")
    return (
        "⚠️ **Вы уверены, что хотите удалить напоминание?**\n"
        "\n"
        f"🔔 **{days} в {time}**\n"
        "\n"
        "*Это действие нельзя отменить.*"
    )


@router.callback_query(F.data.startswith(DEL_REM_PREFIX))
async def reminder_delete_button_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(DEL_REM_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        build_reminder_delete_text(setting),
        reply_markup=build_delete_confirm_keyboard(setting_id),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith(CONFIRM_DEL_REM_PREFIX))
async def reminder_delete_yes_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(CONFIRM_DEL_REM_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await UserSettingRepository(db).delete(setting_id)
    await callback.answer("Запись успешно удалена")
    page = await get_rem_page(state)
    await edit_reminders_page(callback.message, db, callback.from_user.id, page, state)


@router.callback_query(F.data == CANCEL_DEL_REM)
async def reminder_delete_no_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    await callback.answer()
    if isinstance(callback.message, Message):
        page = await get_rem_page(state)
        await edit_reminders_page(callback.message, db, callback.from_user.id, page, state)
