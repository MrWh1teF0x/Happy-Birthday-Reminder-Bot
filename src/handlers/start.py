from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository
from src.handlers.help import maybe_show_help
from src.handlers.states import TimezoneStates
from src.handlers.timezone import request_timezone

router = Router(name="start")

ABOUT_TEXT = (
    "Я помогу не забывать о днях рождения твоих близких: "
    "сохраняй даты через /add_birthday, а я пришлю оповещения заранее."
)


@router.message(CommandStart())
async def start_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    user = message.from_user
    name = user.full_name if user else "друг"
    if user is not None:
        db_user = await UserRepository(db).get_or_create(user.id, username=user.username)
        if db_user.tz_confirmed:
            await message.answer(ABOUT_TEXT)
            await maybe_show_help(db, user.id, message.answer)
            return
    await state.set_state(TimezoneStates.waiting_for_timezone)
    await message.answer(f"Привет, {name}! {ABOUT_TEXT}")
    await request_timezone(message, state)
