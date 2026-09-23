from aiogram.fsm.state import State, StatesGroup


class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()


class BirthdayStates(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_date = State()


class EditBirthdayStates(StatesGroup):
    choosing_field = State()
    waiting_for_value = State()


class ReminderStates(StatesGroup):
    waiting_for_days = State()
    waiting_for_time = State()


class EditReminderStates(StatesGroup):
    choosing_field = State()
    waiting_for_value = State()
