from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository
from src.handlers.states import TimezoneStates
from src.handlers.timezone import request_timezone

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: Message, db: AsyncSession, state: FSMContext) -> None:
    user = message.from_user
    name = user.full_name if user else "друг"
    if user is not None:
        await UserRepository(db).get_or_create(user.id, username=user.username)
    await state.set_state(TimezoneStates.waiting_for_timezone)
    await message.answer(f"Привет, {name}! Я напомню о днях рождения твоих близких. 🎂")
    await request_timezone(message)
