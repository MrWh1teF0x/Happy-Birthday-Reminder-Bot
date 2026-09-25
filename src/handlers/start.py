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

HELP_HINT = "💡 Чтобы узнать обо всех возможностях и увидеть список команд, просто напиши /help"

ABOUT_TEXT = (
    "Я помогу не забывать о днях рождения твоих близких: "
    "сохраняй даты через /add_birthday, а я пришлю оповещения заранее."
    "\n\n" + HELP_HINT
)

GREETING_TEXT = (
    "🎉 Привет {name}! Я — твой личный главный по праздникам!\n"
    "\n"
    "Больше никаких забытых дней рождения, паники в последний момент и неловких оправданий. "
    "Я буду заранее напоминать тебе о важных датах, чтобы ты всегда успевал придумать "
    "отличный подарок и поздравить близких первым!\n"
    "\n"
    "✨ Что я умею:\n"
    "\n"
    "📅 Запоминать дни рождения всех твоих друзей, родных и коллег.\n"
    "\n"
    "🔔 Напоминать о празднике за неделю, за 3 дня или прямо с утра.\n"
    "\n"
    "🎁 Хранить твои заметки с идеями для подарков.\n"
    "\n" + HELP_HINT
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
    await message.answer(GREETING_TEXT.format(name=name))
    await request_timezone(message, state)
