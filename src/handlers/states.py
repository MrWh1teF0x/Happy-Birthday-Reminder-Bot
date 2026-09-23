from aiogram.fsm.state import State, StatesGroup


class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()


class BirthdayStates(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_date = State()
