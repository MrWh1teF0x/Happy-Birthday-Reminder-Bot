"""Оповещения: список, добавление и изменение (за сколько дней и во сколько)."""

import re
from datetime import time as time_type

from aiogram import F, Router
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
from src.handlers.reminder_saver import DbReminderSaver
from src.handlers.states import AddReminderSG, EditReminderStates

router = Router(name="reminders")

EDIT_PREFIX = "reminder:edit:"
TOGGLE_PREFIX = "reminder:toggle:"
DELETE_PREFIX = "reminder:del:"
DELETE_YES_PREFIX = "rdel_yes:"
DELETE_NO_PREFIX = "rdel_no:"
FIELD_PREFIX = "redit:"
ADD_PREFIX = "rem_add:"
ADD_DAYS_PREFIX = "rem_add:days:"
ADD_TIME_PREFIX = "rem_add:time:"
ADD_NEW = "rem_add:new"
ADD_ALL = "rem_add:all"
ADD_BACK = "rem_add:back"
ADD_CANCEL = "rem_add:cancel"
FIELD_DAYS = "days"
FIELD_TIME = "time"

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

DAYS_ERROR_TEXT = "⚠️ Введите корректное число дней (от 0 до 365)"

TIME_ERROR_TEXT = "⚠️ Некорректный формат времени. Используйте формат ЧЧ:ММ (например: `10:00`)."

ADD_CANCELLED_TEXT = "❌ Добавление напоминания отменено."

FIELD_LABELS: dict[str, str] = {
    FIELD_DAYS: "За сколько дней",
    FIELD_TIME: "Во сколько",
}

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


def build_reminders_keyboard(settings: list[UserSetting]) -> InlineKeyboardMarkup:
    rows = []
    for setting in settings:
        toggle_label = "⏸ Выкл" if setting.is_enabled else "▶️ Вкл"
        rows.append(
            [
                InlineKeyboardButton(text="✏️", callback_data=f"{EDIT_PREFIX}{setting.id}"),
                InlineKeyboardButton(
                    text=toggle_label, callback_data=f"{TOGGLE_PREFIX}{setting.id}"
                ),
                InlineKeyboardButton(text="🗑", callback_data=f"{DELETE_PREFIX}{setting.id}"),
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def build_add_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить напоминание", callback_data=ADD_NEW)]
        ]
    )


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


def build_reminder_fields_keyboard(setting_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"{FIELD_PREFIX}{setting_id}:{field}")]
        for field, label in FIELD_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_delete_confirm_keyboard(setting_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить", callback_data=f"{DELETE_YES_PREFIX}{setting_id}"
                ),
                InlineKeyboardButton(text="Нет", callback_data=f"{DELETE_NO_PREFIX}{setting_id}"),
            ]
        ]
    )


async def get_owned_setting(db: AsyncSession, tg_id: int, setting_id: int) -> UserSetting | None:
    setting = await UserSettingRepository(db).get(setting_id)
    if setting is None or setting.tg_id != tg_id:
        return None
    return setting


def render_reminders_text(settings: list[UserSetting]) -> str:
    lines = [f"{i}. {format_reminder(item)}" for i, item in enumerate(settings, 1)]
    return "Твои оповещения:\n\n" + "\n".join(lines)


async def show_reminders_list(message: Message, db: AsyncSession, tg_id: int) -> None:
    settings = await UserSettingRepository(db).list_by_user(tg_id)
    if not settings:
        await message.answer(
            "Оповещений пока нет. Добавь первое: /add_reminder.",
            reply_markup=build_add_keyboard(),
        )
        return
    await message.answer(
        render_reminders_text(settings),
        reply_markup=build_reminders_keyboard(settings),
    )


async def refresh_reminders_list(
    callback: CallbackQuery, db: AsyncSession, prefix: str = ""
) -> None:
    if not isinstance(callback.message, Message):
        return
    settings = await UserSettingRepository(db).list_by_user(callback.from_user.id)
    if not settings:
        await callback.message.edit_text("Список пуст — добавить: /add_reminder.")
        return
    await callback.message.edit_text(
        (prefix + "\n\n" if prefix else "") + render_reminders_text(settings),
        reply_markup=build_reminders_keyboard(settings),
    )


@router.message(Command("reminders_list"))
async def reminders_list_handler(message: Message, db: AsyncSession) -> None:
    if message.from_user is None:
        return
    await show_reminders_list(message, db, message.from_user.id)


async def start_add_flow(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await UserRepository(db).get_or_create(
        message.from_user.id, username=message.from_user.username
    )
    await state.set_state(AddReminderSG.waiting_for_days)
    await message.answer(STEP1_TEXT, reply_markup=build_days_keyboard(), parse_mode="Markdown")


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


async def proceed_to_time(
    state: FSMContext, days: int, edit_message: Message | None, answer_to: Message
) -> None:
    await state.update_data(days=days)
    await state.set_state(AddReminderSG.waiting_for_time)
    if edit_message is not None:
        await edit_message.edit_text(
            STEP2_TEXT, reply_markup=build_time_keyboard(), parse_mode="Markdown"
        )
    else:
        await answer_to.answer(
            STEP2_TEXT, reply_markup=build_time_keyboard(), parse_mode="Markdown"
        )


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
    await proceed_to_time(state, days, callback.message, callback.message)


@router.message(AddReminderSG.waiting_for_days, F.text)
async def reminder_days_handler(message: Message, state: FSMContext) -> None:
    days = parse_days(message.text or "")
    if days is None:
        await message.answer(DAYS_ERROR_TEXT)
        return
    await proceed_to_time(state, days, None, message)


async def finish_add_reminder(
    db: AsyncSession,
    state: FSMContext,
    tg_id: int,
    moment: time_type,
    edit_message: Message | None,
    answer_to: Message,
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
    text = build_finish_text(setting) + "\n\n" + render_reminders_text(settings)
    if edit_message is not None:
        await edit_message.edit_text(
            text, reply_markup=build_finish_keyboard(), parse_mode="Markdown"
        )
    else:
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
    await finish_add_reminder(
        db, state, callback.from_user.id, moment, callback.message, callback.message
    )


@router.message(AddReminderSG.waiting_for_time, F.text)
async def reminder_time_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    moment = parse_time(message.text or "")
    if moment is None:
        await message.answer(TIME_ERROR_TEXT, parse_mode="Markdown")
        return
    await finish_add_reminder(db, state, message.from_user.id, moment, None, message)


@router.callback_query(F.data == ADD_BACK)
async def reminder_back_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddReminderSG.waiting_for_days)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            STEP1_TEXT, reply_markup=build_days_keyboard(), parse_mode="Markdown"
        )


@router.callback_query(F.data == ADD_CANCEL)
async def reminder_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(ADD_CANCELLED_TEXT)


@router.callback_query(F.data == ADD_ALL)
async def reminder_all_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    settings = await UserSettingRepository(db).list_by_user(callback.from_user.id)
    if not settings:
        await callback.message.edit_text(
            "Оповещений пока нет. Добавь первое: /add_reminder.",
            reply_markup=build_add_keyboard(),
        )
        return
    await callback.message.edit_text(
        render_reminders_text(settings),
        reply_markup=build_reminders_keyboard(settings),
    )


@router.message(Command("edit_reminder"))
async def edit_reminder_hint_handler(message: Message) -> None:
    await message.answer(
        "Чтобы изменить оповещение, открой /reminders_list и нажми ✏️ под нужной записью."
    )


@router.callback_query(F.data.startswith(EDIT_PREFIX))
async def reminder_edit_button_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(EDIT_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.set_state(EditReminderStates.choosing_field)
    await state.update_data(setting_id=setting_id)
    await callback.answer()
    await callback.message.edit_text(
        f"{format_reminder(setting)}\n\nЧто изменить?",
        reply_markup=build_reminder_fields_keyboard(setting_id),
    )


# Без фильтра состояния: setting_id уже зашит в callback_data,
# состояние выставляется заново внутри хендлера.
@router.callback_query(F.data.startswith(FIELD_PREFIX))
async def reminder_field_handler(
    callback: CallbackQuery, db: AsyncSession, state: FSMContext
) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        _, setting_id_text, field = callback.data.removeprefix(FIELD_PREFIX).split(":")
        setting_id = int(setting_id_text)
    except ValueError:
        await callback.answer("Некорректное поле.", show_alert=True)
        return
    if field not in FIELD_LABELS:
        await callback.answer("Некорректное поле.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await state.set_state(EditReminderStates.waiting_for_value)
    await state.update_data(setting_id=setting_id, field=field)
    await callback.answer()
    prompt = (
        "Пришли число от 0 до 365."
        if field == FIELD_DAYS
        else "Пришли время в формате ЧЧ:ММ — например, 09:00."
    )
    await callback.message.edit_text(f"{format_reminder(setting)}\n\n{prompt}")


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
            await message.answer("Не понял время. Формат ЧЧ:ММ — например, 09:00.")
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


@router.callback_query(F.data.startswith(TOGGLE_PREFIX))
async def reminder_toggle_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(TOGGLE_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await UserSettingRepository(db).update(setting_id, is_enabled=not setting.is_enabled)
    await callback.answer("Выключено." if setting.is_enabled else "Включено.")
    await refresh_reminders_list(callback, db)


@router.callback_query(F.data.startswith(DELETE_PREFIX))
async def reminder_delete_button_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(DELETE_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None or not isinstance(callback.message, Message):
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        f"Удалить оповещение?\n{format_reminder(setting)}",
        reply_markup=build_delete_confirm_keyboard(setting_id),
    )


@router.callback_query(F.data.startswith(DELETE_YES_PREFIX))
async def reminder_delete_yes_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    try:
        setting_id = int(callback.data.removeprefix(DELETE_YES_PREFIX))
    except ValueError:
        await callback.answer("Некорректная запись.", show_alert=True)
        return
    setting = await get_owned_setting(db, callback.from_user.id, setting_id)
    if setting is None:
        await callback.answer("Запись не найдена.", show_alert=True)
        return
    await UserSettingRepository(db).delete(setting_id)
    await callback.answer("Удалено.")
    await refresh_reminders_list(callback, db, prefix="Готово, удалил.")


@router.callback_query(F.data.startswith(DELETE_NO_PREFIX))
async def reminder_delete_no_handler(callback: CallbackQuery, db: AsyncSession) -> None:
    if callback.from_user is None or callback.data is None:
        return
    await callback.answer()
    await refresh_reminders_list(callback, db)
