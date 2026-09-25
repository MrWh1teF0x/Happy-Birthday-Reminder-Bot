from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import UserRepository
from src.handlers.commands import render_help

router = Router(name="help")


@router.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(render_help())


async def maybe_show_help(
    db: AsyncSession, tg_id: int, send: Callable[[str], Awaitable[Any]]
) -> None:
    """Показывает help один раз: если флаг help_shown ещё не стоит."""
    user = await UserRepository(db).get_by_tg_id(tg_id)
    if user is None or user.help_shown:
        return
    user.help_shown = True
    await db.flush()
    await send(render_help())
