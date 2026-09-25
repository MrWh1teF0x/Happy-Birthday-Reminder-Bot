from aiogram.fsm.state import State, StatesGroup


class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()


class AddBirthdaySG(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()
    waiting_for_note = State()


class EditBirthdaySG(StatesGroup):
    waiting_for_new_name = State()
    waiting_for_new_date = State()
    waiting_for_new_note = State()


class AddReminderSG(StatesGroup):
    waiting_for_days = State()
    waiting_for_time = State()


class EditReminderStates(StatesGroup):
    choosing_field = State()
    waiting_for_value = State()
