from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from templates import HELP_MESSAGE

router = Router()

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    await message.answer(HELP_MESSAGE)
