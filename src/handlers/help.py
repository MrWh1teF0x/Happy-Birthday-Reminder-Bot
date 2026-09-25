from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from src.handlers.commands import render_help

router = Router(name="help")


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(render_help())
