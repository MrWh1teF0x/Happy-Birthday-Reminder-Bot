from aiogram.fsm.state import State, StatesGroup


class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()


class AddBirthdaySG(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_note = State()


class EditBirthdayStates(StatesGroup):
    choosing_field = State()
    waiting_for_value = State()


class AddReminderSG(StatesGroup):
    waiting_for_days = State()
    waiting_for_time = State()


class EditReminderStates(StatesGroup):
    choosing_field = State()
    waiting_for_value = State()
