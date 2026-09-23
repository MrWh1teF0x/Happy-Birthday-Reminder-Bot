from aiogram.fsm.state import State, StatesGroup


class TimezoneStates(StatesGroup):
    waiting_for_timezone = State()
