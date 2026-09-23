from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")


@router.message(CommandStart())
async def start_handler(message: Message) -> None:
    name = message.from_user.full_name if message.from_user else "друг"
    await message.answer(f"Привет, {name}! Я напомню о днях рождения твоих близких за неделю. 🎂")
